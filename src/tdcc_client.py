import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests


BASE_URL = "https://openapi.tdcc.com.tw/v1/opendata"
RAW_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

DATASETS = {
    "bond_master": "1-8-1",
    "cashflow": "1-8-2",
}


def fetch_dataset(dataset_id: str):
    """從 TDCC OpenAPI 取得指定資料集。"""
    url = f"{BASE_URL}/{dataset_id}"

    response = requests.get(
        url,
        timeout=60,
        headers={"User-Agent": "bondscope-tw/0.1"},
    )
    response.raise_for_status()

    return url, response.json()


def extract_records(payload):
    """兼容清單或常見字典格式，取出資料紀錄。"""
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        for key in ("data", "records", "result"):
            records = payload.get(key)
            if isinstance(records, list):
                return records

    return []


def save_raw_data(name: str, dataset_id: str, url: str, payload):
    """完整保存原始資料與下載資訊。"""
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

    retrieved_at = datetime.now(ZoneInfo("Asia/Taipei"))
    timestamp = retrieved_at.strftime("%Y%m%d_%H%M%S")
    output_path = RAW_DATA_DIR / f"{name}_{timestamp}.json"

    raw_document = {
        "dataset_id": dataset_id,
        "source_url": url,
        "retrieved_at": retrieved_at.isoformat(),
        "payload": payload,
    }

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(raw_document, file, ensure_ascii=False, indent=2)

    return output_path


def main():
    for name, dataset_id in DATASETS.items():
        print(f"\n正在下載 {name}（{dataset_id}）……")

        url, payload = fetch_dataset(dataset_id)
        records = extract_records(payload)
        output_path = save_raw_data(
            name=name,
            dataset_id=dataset_id,
            url=url,
            payload=payload,
        )

        print(f"下載成功：{len(records):,} 筆")
        print(f"保存位置：{output_path}")

        if records and isinstance(records[0], dict):
            print("第一筆資料欄位：")
            print(list(records[0].keys()))
        elif not records:
            print("警告：尚未辨識出資料清單，已完整保存原始回應。")


if __name__ == "__main__":
    main()