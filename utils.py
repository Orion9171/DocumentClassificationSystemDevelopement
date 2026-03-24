def load_config(path="config.json"):
    import json
    with open(path, "r") as f:
        return json.load(f)