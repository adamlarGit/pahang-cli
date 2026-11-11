"""Probe opening the XML-joined files in Word COM and compare open times with COM-compiled files."""

from pathlib import Path
import time
import pythoncom
import win32com.client

def measure_word_open(file_path: Path):
    pythoncom.CoInitialize()
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        try:
            t0 = time.perf_counter()
            doc = word.Documents.Open(str(file_path), False, True)
            open_time = time.perf_counter() - t0
            pages = doc.ComputeStatistics(2)  # 2 = wdStatisticPages
            paras = doc.Paragraphs.Count
            doc.Close(False)
            return open_time, pages, paras, None
        except Exception as exc:
            return None, None, None, str(exc)
        finally:
            word.Quit()
    finally:
        pythoncom.CoUninitialize()

def main():
    p3_com = Path(r"C:\Users\ADAM\AppData\Local\Temp\r232\project\FULL REPORT\GEBENG\01. OCTOBER\07-10-2026\01. PPU APMM 3311kV - Part 03 - Panel 1 (33kV - SPARE).docx")
    p3_xml = Path(r"C:\Users\ADAM\Desktop\pahang-cli-33kv\scratch\prototype-flir-xml-join-225\worktree\scratch\output\01. PPU APMM 3311kV - Part 03 - Panel 1 (33kV - SPARE) [XML-JOINED].docx")

    p32_com = Path(r"C:\Users\ADAM\AppData\Local\Temp\r232\project\FULL REPORT\GEBENG\01. OCTOBER\07-10-2026\01. PPU APMM 3311kV - Part 32 - TX and Condition.docx")
    p32_xml = Path(r"C:\Users\ADAM\Desktop\pahang-cli-33kv\scratch\prototype-flir-xml-join-225\worktree\scratch\output\01. PPU APMM 3311kV - Part 32 - TX and Condition [XML-JOINED].docx")

    print("\n--- MEASURING PART 03 OPEN TIME ---")
    t_com, pg_com, pr_com, err_com = measure_word_open(p3_com)
    print(f"Part 03 COM-compiled: open={t_com:.2f}s, pages={pg_com}, paras={pr_com}, error={err_com}")

    t_xml, pg_xml, pr_xml, err_xml = measure_word_open(p3_xml)
    if err_xml:
        print(f"Part 03 XML-joined: ERROR={err_xml}")
    else:
        print(f"Part 03 XML-joined:    open={t_xml:.2f}s, pages={pg_xml}, paras={pr_xml}, error={err_xml}")

    print("\n--- MEASURING PART 32 OPEN TIME ---")
    t32_com, pg32_com, pr32_com, err32_com = measure_word_open(p32_com)
    if err32_com:
        print(f"Part 32 COM-compiled: ERROR={err32_com}")
    else:
        print(f"Part 32 COM-compiled: open={t32_com:.2f}s, pages={pg32_com}, paras={pr32_com}, error={err32_com}")

    t32_xml, pg32_xml, pr32_xml, err32_xml = measure_word_open(p32_xml)
    if err32_xml:
        print(f"Part 32 XML-joined: ERROR={err32_xml}")
    else:
        print(f"Part 32 XML-joined:    open={t32_xml:.2f}s, pages={pg32_xml}, paras={pr32_xml}, error={err32_xml}")

if __name__ == "__main__":
    main()
