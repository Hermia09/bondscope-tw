import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"

GLEIF_API_URL = "https://api.gleif.org/api/v1/lei-records"


def fetch_lei_by_isin(isin: str):
    """使用ISIN查詢GLEIF法人資料。"""
    response = requests.get(
        GLEIF_API_URL,
        params={
            "filter[isin]": isin,
            "page[size]": 10,
        },
        headers={
            "Accept": "application/vnd.api+json",
            "User-Agent": "bondscope-tw/0.1",
        },
        timeout=60,
    )

    response.raise_for_status()
    return response.url, response.json()


def save_raw_response(isin: str, source_url: str, payload):
    """保存GLEIF原始回應及查詢時間。"""
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

    retrieved_at = datetime.now(ZoneInfo("Asia/Taipei"))
    timestamp = retrieved_at.strftime("%Y%m%d_%H%M%S")

    output_path = (
        RAW_DATA_DIR
        / f"gleif_{isin}_{timestamp}.json"
    )

    document = {
        "isin": isin,
        "source_url": source_url,
        "retrieved_at": retrieved_at.isoformat(),
        "payload": payload,
    }

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(
            document,
            file,
            ensure_ascii=False,
            indent=2,
        )

    return output_path


def get_nested_value(data, *keys):
    """安全讀取多層JSON欄位。"""
    current = data

    for key in keys:
        if not isinstance(current, dict):
            return None

        current = current.get(key)

    return current


def main():
    isin = input("請輸入12碼ISIN：").strip().upper()

    if len(isin) != 12 or not isin.isalnum():
        print("ISIN格式錯誤。")
        return

    print(f"正在向GLEIF查詢：{isin}")

    try:
        source_url, payload = fetch_lei_by_isin(isin)
    except requests.RequestException as error:
        print(f"GLEIF查詢失敗：{error}")

        if error.response is not None:
            print(error.response.text[:1000])

        return

    output_path = save_raw_response(
        isin=isin,
        source_url=source_url,
        payload=payload,
    )

    records = payload.get("data", [])

    print(f"查詢結果數量：{len(records)}")
    print(f"原始回應：{output_path}")

    if not records:
        print("GLEIF目前沒有此ISIN的對應資料。")
        print("應標記為：INSUFFICIENT_DATA")
        return

    for index, record in enumerate(records, start=1):
        attributes = record.get("attributes", {})
        entity = attributes.get("entity", {})
        registration = attributes.get("registration", {})

        lei = attributes.get("lei") or record.get("id")

        legal_name = get_nested_value(
            entity,
            "legalName",
            "name",
        )

        legal_country = get_nested_value(
            entity,
            "legalAddress",
            "country",
        )

        headquarters_country = get_nested_value(
            entity,
            "headquartersAddress",
            "country",
        )

        print("\n" + "=" * 50)
        print(f"結果：{index}")
        print(f"LEI：{lei}")
        print(f"法人正式名稱：{legal_name}")
        print(f"法律管轄地：{entity.get('jurisdiction')}")
        print(f"註冊地址國家：{legal_country}")
        print(f"總部地址國家：{headquarters_country}")
        print(f"法人狀態：{entity.get('status')}")
        print(f"LEI登記狀態：{registration.get('status')}")
        print(
            "GLEIF最後更新："
            f"{registration.get('lastUpdateDate')}"
        )


if __name__ == "__main__":
    main()