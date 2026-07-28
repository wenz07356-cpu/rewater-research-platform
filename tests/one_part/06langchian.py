from langchain_text_splitters import RecursiveCharacterTextSplitter




splitter = RecursiveCharacterTextSplitter(
    chunk_size=10,
    chunk_overlap=0,
    separators=['/n','。']
)


test_text = ("AB。CD。HHEFG。HIJ。KLM。/nNHHHOPQRSHHHHHHTU。VWSYZhhhhhhhh。/n")

chunks = splitter.split_text(test_text)
for i, chunk in enumerate(chunks):
    print(f"--- 第{i+1}块 (长度：{len(chunk)}) ---")
    print(chunk)
    print()