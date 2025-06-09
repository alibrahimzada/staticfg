class DFGBuilder:
    def __init__(self, cfg):
        self.cfg = cfg

    def build_paths(self):
        return []

    def write_paths(self, filepath: str):
        with open(filepath, 'w') as f:
            pass
