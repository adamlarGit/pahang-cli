from zipfile import ZipFile
from io import BytesIO
import olefile
import re

with ZipFile('.scratch/prod-proof/data/talapia.docx') as z:
    for i in range(1, 28):
        bin_name = f'word/activeX/activeX{i}.bin'
        data = z.read(bin_name)
        fd_count = len(re.findall(rb"_Fd\d+", data))
        tag_count = data.count(b"TAG_R8_FLD")
        print(f"activeX{i:2d}.bin: size={len(data):7d}, TAG_R8_FLD={tag_count}, _Fd={fd_count}")
