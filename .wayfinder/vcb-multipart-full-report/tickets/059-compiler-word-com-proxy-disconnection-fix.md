Part of #55
Specification: [spec.md](../spec.md)

# 059: fix(compiler): handle Word COM proxy invalidation on SaveAs2 in WordComDocumentCompiler

**What to build:** In `WordComDocumentCompiler.compile()`, when saving a newly assembled Word document via `main_doc.SaveAs2(output_path)`, Microsoft Word converts the in-memory document moniker to a disk-backed document file and invalidates/disconnects the original COM proxy reference (`main_doc`). Subsequent direct calls on `main_doc.Close(False)` throw `RPC_E_DISCONNECTED` (`-2147417848` / `0x80010108`: 'The object invoked has disconnected from its clients.'), causing full report batch generation to fail even though the output file was successfully written to disk. Fix `WordComDocumentCompiler.compile()` to gracefully handle proxy disconnection after `SaveAs2`: safely close the document handle without raising a false error if the file has been successfully persisted, and ensure any lingering open document handle in `word_app.Documents` is closed cleanly.

**Blocked by:** None (can start immediately).

<!-- status: closed -->
**Status**: closed

- [x] In `src/quick_report/compiler.py`: catch and handle `RPC_E_DISCONNECTED` on `main_doc.Close(False)` after successful `main_doc.SaveAs2()`, ensuring the document handle is cleaned up and the compiled output path is returned.
- [x] Ensure `word_app.Documents.Count` is 0 after successful compilation without lingering open handles.
- [x] Add unit/mock tests in `tests/test_quick_report_composer_com.py` reproducing and verifying the proxy disconnection handling.
- [x] Verify with real end-to-end full report generation on `CKTN/PCE/J01546` (`PERPUSTAKAAN AWAM(VCB)`).
