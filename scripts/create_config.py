import os
import yaml

CONFIG = {
    "GOODS_TOOLS_DIR": "/Users/sysilion/goods_tools",
    "CSV_PATTERNS": [
        ["must_eat_data_*.csv", "redtable", True],
        ["ydp_store_data_*.csv", "ydp", False],
        ["store_data_*.csv", "benepia", False],
    ],
    "GEOCODE_DELAY_S": 1.0,
    "GEOCODE_TIMEOUT_S": 10
}

def save_config(filepath="config.yaml"):
    with open(filepath, "w", encoding="utf-8") as f:
        yaml.dump(CONFIG, f)

if __name__ == "__main__":
    save_config()
