from zipfile import ZipFile
from io import BytesIO
import olefile
import re

FD = re.compile(rb"_Fd\d+")

with ZipFile('.scratch/prod-proof/data/talapia.docx') as z:
    for bin_name in ['word/activeX/activeX11.bin', 'word/activeX/activeX18.bin']:
        data = z.read(bin_name)
        print(f"=== {bin_name} (size {len(data)}) ===")
        print("TAG_R8_FLD in raw binary:", data.count(b"TAG_R8_FLD"))
        print("_Fd matches in raw binary:", [m.decode() for m in set(FD.findall(data))])
        if olefile.isOleFile(BytesIO(data)):
            with olefile.OleFileIO(BytesIO(data)) as ole:
                print("OLE root clsid:", ole.root.clsid)
                for entry in ole.listdir(streams=True, storages=False):
                    stream_data = ole.openstream(entry).read()
                    print(f"  Stream {'/'.join(entry)}: size={len(stream_data)}, TAG_R8_FLD={stream_data.count(b'TAG_R8_FLD')}, _Fd={set(FD.findall(stream_data))}")
