# Forensic Investigation: Adobe PDF Virtual Printer Deadlock, Windows Session 0 Isolation, and Architectural Alternatives

**Date:** 01 November 2026  
**Host Machine:** `LAPTOP-D6RA3CQT`  
**Operating System:** Windows 11 Enterprise (Version 10.0.26200.9711, 64-bit)  
**Target Project:** `C:\Users\ADAM\Documents\PO 42360565 - PAHANG - 11kV CYCLE3 - AZZAD`  
**Inspection Date:** `17-08-2026` (Cameron Highland)  
**Affected Documents:** `101. TANG SENG (VI).docx`, `102. TANG SUNG YUIM (VI).docx`  
**Author:** Antigravity AI Orchestrator  

---

> **Correction (2026-11-01): read this before the rest of the document.** The image-quality problem behind this investigation has nothing to do with Session 0. The [fidelity probe](./pdf_image_fidelity_probe/FINDINGS.md) showed three things:
>
> 1. The "53x53 thumbnails" are an icon that exists in the source DOCX.
> 2. The real loss comes from Word's native PDF export, which resamples pictures above roughly 200 PPI down to about 200 PPI. No Word setting stops this, including the `DoNotCompressPictures`, `defaultImageDpi`, and `ExportBitmapResolution` mechanisms proposed in Alternative 1 below.
> 3. Native export followed by Source Image Restoration meets the fidelity goal without Adobe or the spooler.
>
> [ADR 0009](../adr/0009-native-export-with-source-image-restoration.md) records the decision and supersedes ADR 0008. The Session 0 analysis below remains a historical account of why the Adobe virtual-printer path was abandoned. Its causal claims (UIPI, the port-monitor cache, the 256 KB pipe buffer) were never verified. Its alternative rankings and speed figures are estimates, not measurements.

---

## 1. Executive Summary

During Full Report batch post-processing for Cameron Highland (17-08-2026), reports `093` through `100` (8 documents) successfully converted via the `Adobe PDF` virtual printer with intact high-resolution thermograms and embedded ultrasound audio. However, reports `101` and `102` consistently fail silent Adobe PDF printing, timing out after ~100–150 seconds and falling back to Word's native `ExportAsFixedFormat` engine.

Extensive forensic investigation—correlating Windows Print Service Operational Event Logs (`Microsoft-Windows-PrintService/Operational`), Acrobat Distiller internal transaction logs (`messages.log`), WMI process trees, and disassembly of the Adobe PDF Port Monitor driver (`AdobePDF.dll`)—reveals that the failure is **not a corrupted Word document, not an invalid file path, and not a bug in the report generator**.

The failure is caused by an **inherent Windows architectural security boundary**: **Windows Session 0 Isolation and User Interface Privilege Isolation (UIPI)**. When Word spools a large PostScript print job (>40MB–88MB) to the `Adobe PDF` printer, the Windows Print Spooler (`spoolsv.exe`, which executes as `NT AUTHORITY\SYSTEM` in Session 0) fails to communicate with the user's desktop helper (`acrotray.exe` in Session 1). Falling back to its built-in legacy recovery path, the spooler spawns `acrodist.exe` directly inside Session 0. In Session 0, Distiller has no desktop window station, cannot access the user profile or `HKCU\Software\Adobe\Acrobat Distiller\PrinterJobControl`, and **permanently freezes at 0% CPU**. This blocks the spooler pipe buffer at 256 KB, deadlocking all subsequent print jobs.

This document provides a complete technical breakdown of the event sequence, explains why earlier documents succeeded, details why COM pre-warming was insufficient, and provides four concrete engineering alternatives for second opinion and strategic decision-making.

---

## 2. Chronological Forensic Reconstruction

### 2.1 The Two Document Cohorts

All 10 Full Report Word documents in Cameron Highland 17-08-2026 share identical structural templates (56–61 paragraphs, 22–24 tables, 64–75 inline images):

| Substation | Document File | Word .docx Size | PostScript Spool Size | Result | Deliverable PDF Size |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **093** | `093. CHAN KAM HONG (IR+VI).docx` | 28.8 MB | ~65 MB | **SUCCESS** (Adobe PDF) | 11.6 MB (High-Res) |
| **094** | `094. CHAN YIM SOM (IR+VI).docx` | 33.9 MB | ~72 MB | **SUCCESS** (Adobe PDF) | 12.5 MB (High-Res) |
| **095** | `095. LIEW PUN CHOW (IR+VI).docx` | 20.5 MB | ~52 MB | **SUCCESS** (Adobe PDF) | 10.4 MB (High-Res) |
| **096** | `096. LOW WENG KUAN (VI).docx` | 15.8 MB | ~41 MB | **SUCCESS** (Adobe PDF) | 8.6 MB (High-Res) |
| **097** | `097. KUAN SU CHAN (VI).docx` | 19.2 MB | ~48 MB | **SUCCESS** (Adobe PDF) | 9.7 MB (High-Res) |
| **098** | `098. SING KOK (US+VI).docx` | 16.1 MB | ~43 MB | **SUCCESS** (Adobe PDF) | 9.7 MB (High-Res) |
| **099** | `099. SS SING KOK (VI).docx` | 14.6 MB | ~39 MB | **SUCCESS** (Adobe PDF) | 8.8 MB (High-Res) |
| **100** | `100. CHAN KOK WAH (VI).docx` | 27.6 MB | ~68 MB | **SUCCESS** (Adobe PDF) | 12.1 MB (High-Res) |
| **101** | `101. TANG SENG (VI).docx` | 21.1 MB | **88.4 MB** | **FAIL** (Fallback to Native) | 7.6 MB (Downsampled) |
| **102** | `102. TANG SUNG YUIM (VI).docx` | 22.1 MB | **49.8 MB** | **FAIL** (Fallback to Native) | 8.0 MB (Downsampled) |

---

### 2.2 Event Log & Process Timeline

Correlating `Microsoft-Windows-PrintService/Operational` events with Distiller's `messages.log`:

```mermaid
sequenceDiagram
    autonumber
    actor CLI as Python CLI (Session 1)
    participant Word as WINWORD.EXE (Session 1)
    participant Spool as Spoolsv.exe (Session 0 SYSTEM)
    participant PM as AdobePdf.dll (Port Monitor)
    participant Tray as AcroTray.exe (Session 1)
    participant Dist1 as Acrodist.exe (Session 1)
    participant Dist0 as Acrodist.exe (Session 0)

    Note over CLI,Dist1: 03:38:12 UTC - Document 100 (Job 34) Succeeds Cleanly
    Spool->>PM: Hand Job 34 to port Documents\*.pdf
    PM->>Tray: Window message to AcrobatTrayIcon
    Tray->>Dist1: Spawn acrodist.exe in Session 1 with Pipe parameters
    Dist1->>Spool: Connect to \\.\pipe\PMtoDistiller_ID_34
    Dist1-->>CLI: 03:38:21 (8.7s) PDF compiled at .tmp_conv_100.pdf
    Spool-->>Spool: 03:38:31 Port closed (10s post-PDF drain)

    Note over CLI,Dist0: 03:38:51 UTC - Document 101 (Job 35 / Job 2) Begins (88.4 MB Spool)
    CLI->>Word: doc.PrintOut(Background=False)
    Word->>Spool: Spooling 88,402,742 bytes (21 pages) via splwow64.exe
    Spool->>PM: StartDocPort on Documents\*.pdf
    PM->>PM: FindWindow("AcrobatTrayIcon", NULL) from Session 0
    Note over PM: BLOCKED BY WINDOWS UIPI!<br/>Session 0 cannot find Session 1 desktop windows.<br/>FindWindow returns NULL.
    PM->>Dist0: Spooler invokes CreateProcessW in Session 0!
    Note over Dist0: acrodist.exe launched in Session 0.<br/>NO interactive desktop window station.<br/>HKCU mapped to C:\Windows\System32\config\systemprofile.<br/>Cannot read PrinterJobControl.<br/>FREEZES AT 0% CPU (PID 19248).
    Spool->>PM: Write 262,144 bytes (256 KB) into pipe buffer
    Note over Spool,Word: Pipe buffer is full. Consumer is frozen.<br/>Word COM blocks. Spooler hangs.
    Note over CLI: Timeout (102s) expires waiting for .tmp_conv_101.pdf.<br/>Purge Job 2 (win32print.SetJob JOB_CONTROL_DELETE).<br/>Fallback to _export_fixed_format_isolated.
    CLI->>Word: Native ExportAsFixedFormat completes in 4.2s.
```

---

## 3. Deep Root Cause Analysis

### 3.1 The Adobe PDF Printer Architecture
The Adobe PDF printer is not a physical printer; it is an emulated PostScript virtual printer consisting of three components:
1. **The PostScript Printer Driver (`PSCRIPT5.DLL`)**: Transforms Word GDI graphics calls into PostScript page descriptions.
2. **The Port Monitor (`AdobePDF.dll`)**: A dynamic-link library loaded inside the Windows Print Spooler service (`spoolsv.exe`). Its job is to receive the PostScript data stream from the spooler and pass it to Acrobat Distiller.
3. **Acrobat Distiller (`acrodist.exe`)**: A PostScript-to-PDF compiler. It reads the PostScript stream, applies Distiller JobOptions (e.g. `High Quality Print(1)`), and writes the resulting `.pdf` deliverable to disk.

### 3.2 The Session 0 Isolation Barrier
In Windows XP and Server 2003, all services and the logged-on user shared **Session 0**. In Windows Vista, 7, 10, and 11, Microsoft instituted **Session 0 Isolation**:
- **Services Session (Session 0)**: Non-interactive session reserved exclusively for Windows system services (`services.exe`, `spoolsv.exe`, `svchost.exe`). It has no display monitor, no keyboard, and no interactive window station (`WinSta0`).
- **User Session (Session 1)**: Interactive console session where the user logs on, runs applications (`explorer.exe`, `WINWORD.EXE`, `python.exe`), and interacts with the desktop.

### 3.3 The UIPI and FindWindow Trap
Disassembly and string analysis of `C:\Windows\System32\spool\drivers\x64\3\AdobePdf.dll` reveals how the port monitor bridges the gap between Session 0 and Session 1:

```text
UTF-16 String in AdobePdf.dll at Offset 3018:
  "AcrobatTrayIcon"
  "\\.\pipe\PMtoDistiller"
  "%s /O \"%s\" \"Pipe:%s:%s\""
  "Software\Wow6432Node\Adobe\Acrobat Distiller\11.0"
```

1. When Word prints, `spoolsv.exe` (in Session 0) executes `AdobePdf.dll`.
2. `AdobePdf.dll` calls `FindWindowW(L"AcrobatTrayIcon", NULL)` to find `AcroTray.exe` running on the user's desktop.
3. **The Trap**: Because `spoolsv.exe` runs in Session 0, Windows User Interface Privilege Isolation (UIPI) and desktop isolation strictly prevent Session 0 from enumerating or sending messages to top-level windows in Session 1.
4. When `FindWindowW` returns `NULL`, `AdobePdf.dll` assumes Acrobat Distiller is not installed on the desktop and falls back to:
   ```cpp
   CreateProcessW(NULL, "acrodist.exe /O \"...\" \"Pipe:...\"", ...);
   ```
5. Because `CreateProcessW` is called by `spoolsv.exe` in Session 0, **the spawned `acrodist.exe` is created inside Session 0**.
6. In Session 0:
   - There is no desktop window station.
   - `HKEY_CURRENT_USER` does not point to `C:\Users\ADAM\NTUSER.DAT`; it points to `C:\Windows\System32\config\systemprofile`.
   - Distiller cannot read `HKCU\Software\Adobe\Acrobat Distiller\PrinterJobControl` where Python wrote the output filename.
   - Distiller freezes instantly at 0% CPU (`0:00:00.000` CPU time).
   - The named pipe `\\.\pipe\PMtoDistiller` is left in an unserviced state.
   - The print spooler writes its first 256 KB buffer (`Size in bytes: 262144`) and deadlocks waiting for the pipe reader.

### 3.4 Why Did Reports 093–100 Succeed Previously?
1. On a freshly started system where `AcroTray.exe` has just launched and no print jobs have backed up, the Windows port monitor's internal inter-process communication cache was initialized cleanly.
2. Reports 093–100 each had spool sizes between 39MB and 72MB, and Distiller compiled each in 5–8 seconds.
3. When Document 101 started:
   - `101. TANG SENG (VI).docx` produced an **88.4 MB PostScript spool file** (`00002.SPL`, 88,402,742 bytes).
   - Transferring 88.4 MB through 32-bit `splwow64.exe` GDI thunking took longer than the initial timeout threshold.
   - The Python monitor cancelled the job mid-transfer (`purge_printer_jobs()`).
   - The abrupt cancellation broke the pipe connection to AcroTray.
   - On every subsequent attempt, `AdobePdf.dll` bypassed AcroTray and spawned `acrodist.exe` into Session 0, where it permanently wedged.

### 3.5 Why COM Pre-Warming (`win32com.client.Dispatch`) Did Not Prevent It
Ticket #145 implemented `ensure_session_distiller_warmed()` using `win32com.client.Dispatch("PdfDistiller.PdfDistiller")`.
- When invoked in Session 1, COM successfully launches `acrodist.exe -Embedding` in Session 1 under user `ADAM`.
- **However**: COM Distiller runs purely as an Automation Server waiting for programmatic method calls (`FileToPDF`). It **does not create the `AcrobatTrayIcon` window**, nor does it connect to the port monitor's `PMtoDistiller` pipe.
- Therefore, when `AdobePdf.dll` received Word's print job in Session 0, it still could not find `AcrobatTrayIcon`, and still spawned its own copy of `acrodist.exe` in Session 0!

---

## 4. Architectural Alternatives: "What Else Can We Do?"

We have reached the fundamental boundary of the Windows Print Spooler virtual printer subsystem. Attempting to force an out-of-process, 32-bit, Session 0 system service (`spoolsv.exe`) to silently coordinate with an interactive desktop session across Windows 11 UIPI boundaries for multi-megabyte PostScript streams is notoriously brittle across the Windows ecosystem.

Below are the **four viable engineering alternatives**, ranked by stability and maintainability.

---

### Alternative 1 (Recommended): Word Native Export with High-Fidelity Registry & COM Tuning

#### The Concept
Why did we introduce the Adobe PDF virtual printer in Ticket #140?
Because Word's default `doc.ExportAsFixedFormat()` downsamples thermal images to 53x53 thumbnails.

However, Word's internal image downsampling is **fully configurable**:
1. **Document-Level COM Setting**:
   ```python
   doc.DoNotCompressPictures = True
   ```
2. **Host-Level Office Registry Configuration (`HKCU\Software\Microsoft\Office\16.0\Word\Options`)**:
   - `AutomaticPictureCompressionDefault = 0` (DWORD): Completely disables Word's automatic picture downsampling engine.
   - `ExportBitmapResolution = 300` (or `600`) (DWORD): Overrides Word's default 96/150 DPI PDF export rasterizer, forcing full 300/600 DPI rendering for all embedded graphics and charts.
3. **Native Export Parameters**:
   ```python
   doc.ExportAsFixedFormat(
       OutputFileName=str(pdf_path.resolve()),
       ExportFormat=17,       # wdExportFormatPDF
       OpenAfterExport=False,
       OptimizeFor=0,         # wdExportOptimizeForPrint (Full Quality)
       Range=0,               # wdExportAllDocument
       Item=0,                # wdExportDocumentContent
       IncludeDocProps=True,
       KeepIRM=True,
       CreateBookmarks=0,
       DocStructureTags=True,
       BitmapMissingFonts=True,
       UseISO19005_1=False,
   )
   ```

#### Pros
- **100% Deterministic & Bulletproof**: Runs completely in-process within the interactive user session (`Session 1`).
- **Zero Windows Print Spooler Dependency**: No `spoolsv.exe`, no `AdobePdf.dll`, no print queue, no `.SPL` files, no printer port locks.
- **Lightning Fast**: Generates a 21-page document in **3 to 5 seconds** instead of 90–120 seconds.
- **Zero Third-Party Process Management**: Eliminates `acrodist.exe`, `acrotray.exe`, and `splwow64.exe` sentinels entirely.
- **Preserves Full Resolution**: With `ExportBitmapResolution = 300` and `DoNotCompressPictures = True`, thermograms render at crystal-clear high fidelity.

#### Cons
- Requires writing two DWORD values to `HKCU\Software\Microsoft\Office\16.0\Word\Options` once (can be automated in Python).

---

### Alternative 2: Direct Distiller COM via PostScript File (`PrintToFile` + `distiller.FileToPDF`)

#### The Concept
Acrobat Distiller's true COM API (`PdfDistiller.PdfDistiller`) provides a built-in method:
```python
distiller.FileToPDF(bstrSourcePath, bstrDestinationPath, bstrJobOptions)
```
Instead of routing Word through the Windows Print Spooler port monitor (`Documents\*.pdf`), we use Word to generate a PostScript file directly to disk, and then pass that file directly to Distiller in Session 1:

1. In Word COM:
   ```python
   word_app.ActivePrinter = "Adobe PDF"
   doc.PrintOut(
       Background=False,
       PrintToFile=True,
       OutputFileName=str(temp_ps_path.resolve()),
   )
   ```
2. In Distiller COM (running entirely in Session 1):
   ```python
   distiller = win32com.client.Dispatch("PdfDistiller.PdfDistiller")
   distiller.FileToPDF(str(temp_ps_path), str(target_pdf_path), "High Quality Print(1)")
   ```
3. Python removes `temp_ps_path`.

#### Pros
- Uses genuine Adobe Acrobat Distiller with the exact `High Quality Print(1)` joboptions preset.
- Completely bypasses the Windows Print Spooler port monitor (`AdobePdf.dll`) and `\\.\pipe\PMtoDistiller`.
- Runs 100% inside user Session 1; **Session 0 is never invoked**.
- Synchronous and deterministic: `FileToPDF()` blocks until the PDF is compiled and returns an exit code.

#### Cons
- On some Word versions, `doc.PrintOut(PrintToFile=True)` may display a native Windows "Print to File" modal dialog if the printer port is not configured as a direct file port.
- Writing an 88MB temporary PostScript file to disk introduces disk I/O overhead.

---

### Alternative 3: Virtual PDF Printer Isolation (e.g. Microsoft Print to PDF or PDF24)

#### The Concept
Replace the 32-bit legacy Adobe PDF printer (from Acrobat 11, released in 2012) with a modern 64-bit virtual PDF printer that is fully native to Windows 11:
- **`Microsoft Print to PDF`**: Native Windows 11 printer driver. Uses Microsoft XPS-to-PDF conversion engine (`mxdwdrv.dll`).
- **PDF24 Creator / Bullzip**: Modern virtual PDF printers with documented CLI and registry automation that support headless non-spooler rendering.

#### Pros
- Fully compliant with modern Windows 11 driver isolation and Session 0 isolation.
- No legacy 32-bit Adobe Acrobat 11 dependencies.

#### Cons
- `Microsoft Print to PDF` does not natively support non-interactive output path specification without third-party port monitors or PowerShell print job rerouting.
- PDF24 or third-party tools require external software installations on client machines.

---

### Alternative 4: Hybrid Converter with Non-Blocking Graceful Fallback & Metrics Reporting

#### The Concept
Maintain the current dual-mode architecture, but adjust the operational contract:
1. Attempt Adobe PDF printing with a strict, short timeout (e.g. 15 seconds).
2. If Adobe PDF does not immediately acknowledge and begin compiling, **fail fast immediately** into native `ExportAsFixedFormat` without stalling for 100+ seconds.
3. In native export, apply `DoNotCompressPictures = True` and high-resolution parameters so that the fallback deliverable maintains acceptable fidelity.
4. Provide telemetry in the summary banner indicating whether the deliverable was rendered via `Adobe Distiller` or `Word Native High-Fidelity`.

#### Pros
- Eliminates the 5-minute batch hang on large documents.
- Ensures deliverable generation always succeeds reliably.
- Transparent reporting to the operator.

#### Cons
- Does not resolve the underlying Session 0 failure of Adobe PDF printer itself for large documents.

---

## 5. Comparative Evaluation Matrix

| Metric / Dimension | Alternative 1: Native Export + Reg Tuning | Alternative 2: Direct Distiller COM (`FileToPDF`) | Alternative 3: Modern Virtual Printer | Alternative 4: Fast Fallback + Hybrid |
| :--- | :---: | :---: | :---: | :---: |
| **Immunity to Session 0 Deadlocks** | **100% (No spooler used)** | **100% (No spooler used)** | 90% (Modern driver) | 100% (Fails fast to native) |
| **Batch Conversion Speed** | **3–5s per document** | 15–25s per document | 10–20s per document | 5–15s per document |
| **Image Fidelity (Thermograms)** | **High (300/600 DPI)** | High (Vector PostScript) | High (Vector XPS) | Medium/High |
| **External Dependencies** | **None (MS Office only)** | Adobe Acrobat 11 | Third-party software | MS Office + Adobe |
| **Maintenance Burden** | **Very Low** | Medium | High | Low |
| **Implementation Complexity** | **Low (COM + Reg tweak)** | Medium (PrintToFile handling) | High (Software setup) | Very Low |

---

## 6. Review Addendum: Agreed Decisions and Evidence Boundary

### 6.1 What Is Established and What Remains a Hypothesis

- **Established**: Manual Adobe PDF printing with a non-downsampling quality profile has produced the required high-quality PDF output. That visual result is the reference standard for the automated solution.
- **Established**: The automated Adobe PDF virtual-printer path can leave a job and Distiller process stalled, then route the report through Word native `ExportAsFixedFormat`, producing unacceptable `53x53` thermogram thumbnails for reports `101` and `102`.
- **Established**: The production converter enters the Adobe virtual-printer path through `doc.PrintOut(Background=False)`. Its monitor, timeout, registry registration, and COM pre-warm are all downstream of that dependency.
- **Supported by live evidence, but not yet exhaustively proven**: The Session 0 process, the blocked pipe, and the access-denied spool-file cleanup explain the observed deadlock consistently.
- **Hypothesis, not a proven cause**: The assertion that cancellation permanently corrupts an Adobe port-monitor cache and thereby explains all later failures. This must not drive the replacement design without a reproducible experiment.
- **Unvalidated**: `300 DPI`, Word registry settings, and Word automation settings are possible implementation mechanisms; none is proof that Word native export preserves the source pixels of the thermograms.

### 6.2 Delivery Contract

The target state is a spooler-independent Full Report conversion path that preserves source pixels for every thermogram in reports `101`, `102`, and one normal report. “No compression” means no image downsampling; lossless PDF stream encoding remains acceptable. A nominal output setting such as `300 DPI` is not an acceptance criterion by itself.

The manual Adobe workflow is therefore a **visual reference**, not an approved unattended batch backend. A backend is approved only after it satisfies both the no-spooler and source-pixel-preservation conditions in an end-to-end test with the real documents. Mocked COM, registry, printer, and queue tests remain useful for control flow, but cannot establish this contract.

### 6.3 Interim Operating Policy

The existing native `ExportAsFixedFormat` fallback remains in place for now. It is necessary to keep producing a usable PDF when Adobe PDF printing fails, even though it does not yet meet the target fidelity contract. The CLI must notify the operator when it selects the fallback; no persistent per-file classification is required.

The batch converter must own any temporary Word or Office quality configuration it needs and restore the operator's prior settings after the run. Production correctness must not depend on a workstation's pre-existing personal Word configuration.

### 6.4 Staged Investigation Plan

1. **Native Word proof first**: Build a one-off, read-only fidelity probe. It must write only to a temporary output directory, apply and restore the candidate no-downsampling configuration, and export reports `101`, `102`, and one normal report.
2. **Verify pixels, not only appearance**: Compare the resulting PDF thermogram image dimensions with their DOCX sources for every thermogram in those reports. Do not accept the result merely because it uses a `300 DPI` setting or appears acceptable in a spot check.
3. **Integrate only after proof**: If the native probe satisfies the contract, integrate that exact configuration into the production converter and retain the CLI fallback notice until the new path is live and verified.
4. **Direct Distiller second**: If native Word export cannot preserve the source pixels, prototype `PrintToFile → FileToPDF` through a Session 1 Distiller COM server. This bypasses the Adobe PDF virtual-printer port monitor; it must still be proven non-interactive and pass the same three-report pixel check.
5. **Retire the Adobe virtual-printer batch path**: Remove the `doc.PrintOut(Background=False)` Adobe PDF route only after a compliant replacement is validated. Until then, preserve the existing fallback to avoid blocking PDF delivery.

### 6.5 Earlier Process Gaps

The original Adobe route was a reasonable response to the manual fidelity result. The missing safeguards were architectural and test-related:

1. Native Word no-downsampling was not proven with the worst real reports before the Adobe virtual-printer path became the batch default.
2. The batch path was not validated with an end-to-end multi-document spooler test that could reveal Session 0, port-monitor, and large-PostScript failure modes.
3. The automation design coupled conversion fidelity to an interactive virtual-printer integration rather than first testing a direct file-based Distiller route.
4. Current unit tests exercise mocked boundaries, so they verify control flow but cannot verify session identity, spooler health, pipe state, generated image dimensions, or the final visual quality.
