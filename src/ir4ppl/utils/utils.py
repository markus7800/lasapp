
    
def get_line_offsets(file_name: str) -> list[int]:
    with open(file_name, encoding="utf-8") as f:
        line_offsets: list[int] = []
        cumsum = 0
        for line in f:
            line_offsets.append(cumsum)
            cumsum += len(line)
        
        line_offsets.append(cumsum)
        return line_offsets
    

def get_line_offsets_for_str(s: str) -> list[int]:
    line_offsets: list[int] = []
    cumsum = 0
    for line in s.splitlines(keepends=True):
        line_offsets.append(cumsum)
        cumsum += len(line)
    
    line_offsets.append(cumsum)
    return line_offsets

class FileContent:
    def __init__(self, source: str):
        self.source = source
    def __len__(self):
        return len(self.source)
    def __getitem__(self, i):
        return self.source[i]
    
def get_file_content(file_name: str):
    with open(file_name, encoding="utf-8") as f:
        source = f.read()
        return FileContent(source)