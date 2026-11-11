import json

with open('.scratch/talapia_inspect.json', encoding='utf-8-sig') as f:
    data = json.load(f)[0]

owners = data.get('binary_field_owners', {})
dup_names = {'_Fd715416184', '_Fd632321712', '_Fd1762046236', '_Fd1155285986', '_Fd912557116', '_Fd1961634598', '_Fd926064389', '_Fd1206794782', '_Fd1861462833'}

for d in dup_names:
    print(f"{d}: binary owners = {owners.get(d)}")
