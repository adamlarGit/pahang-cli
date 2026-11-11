import pythoncom
from pathlib import Path

flir_bin = Path(r"C:\Program Files (x86)\FLIR Systems\FLIR Word Reporting\bin")

for dll in sorted(flir_bin.glob("*.dll")):
    try:
        tlb = pythoncom.LoadTypeLib(str(dll))
        print(f"\n=== {dll.name} (TypeInfo count: {tlb.GetTypeInfoCount()}) ===")
        for i in range(tlb.GetTypeInfoCount()):
            doc = tlb.GetDocumentation(i)
            ti = tlb.GetTypeInfo(i)
            attr = ti.GetTypeAttr()
            funcs = []
            for fi in range(attr.cFuncs):
                fd = ti.GetFuncDesc(fi)
                funcs.append(ti.GetNames(fd.memid)[0])
            print(f"  [{i}] {doc[0]} (kind={attr.typekind}, funcs={len(funcs)}): {', '.join(funcs[:10])}")
    except Exception:
        pass
