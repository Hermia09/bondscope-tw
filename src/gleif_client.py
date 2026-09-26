import json
import sqlite3
from datetime import datetime
from pathlib import Path

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
DATABASE_PATH = PROJECT_ROOT / "data" / "bondscope.db"

GLEIF_API_URL = "https://api.gleif.org/api/v1/lei-records"


def validate_isin(isin):
    isin = isin.strip().upper()

    if len(isin) != 12 or not isin.isalnum():
        raise ValueError("ISIN 必須是12碼英文字母或數字。")

    return isin


def save_not_mapped(conn, isin, response_url, raw_file, retrieved_at):
    conn.execute(
        """
        INSERT OR IGNORE INTO security_evidence (
            isin,
            source_name,
            source_type,
            result_status,
            source_url,
            evidence_summary,
            supports_russian_nexus,
            retrieved_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            isin,
            "GLEIF",
            "ISIN_TO_LEI",
            "NOT_MAPPED",
            response_url,
            f"GLEIF查詢結果為0筆；原始回應：{raw_file.name}",
            None,
            retrieved_at,
        ),
    )

    # 只有新案件才建立資料不足紀錄。
    # 已經確認的俄債資料不會被 GLEIF 的0筆結果覆蓋。
    conn.execute(
        """
        INSERT OR IGNORE INTO security_risk_assessment (
            isin,
            issuer_name,
            issuer_country,
            classification,
            confidence,
            review_status,
            updated_at,
            notes
        )
        VALUES (?, NULL, NULL, ?, ?, ?, ?, ?)
        """,
        (
            isin,
            "INSUFFICIENT_DATA",
            "LOW",
            "PENDING_REVIEW",
            retrieved_at,
            "GLEIF沒有ISIN對應資料，需查詢其他官方來源。",
        ),
    )


def save_gleif_match(
    conn,
    isin,
    record,
    response_url,
    raw_file,
    retrieved_at,
):
    attributes = record.get("attributes", {})
    entity = attributes.get("entity", {})

    lei = attributes.get("lei")
    issuer_name = (
        entity.get("legalName", {}).get("name")
        or "UNKNOWN"
    )
    issuer_country = (
        entity.get("legalAddress", {}).get("country")
        or entity.get("headquartersAddress", {}).get("country")
    )

    if issuer_country == "RU":
        classification = "POTENTIAL_RUSSIAN_NEXUS"
        confidence = "MEDIUM"
        supports_russian_nexus = 1
        note = "GLEIF顯示法人註冊地或地址國家為RU，仍需第二來源確認債券性質。"
    else:
        classification = "ISSUER_IDENTIFIED"
        confidence = "MEDIUM"
        supports_russian_nexus = 0
        note = "已找到法人資料，但不能只靠GLEIF判定為非俄債。"

    evidence_summary = (
        f"LEI={lei}；發行人={issuer_name}；"
        f"國家={issuer_country or 'UNKNOWN'}；"
        f"原始回應={raw_file.name}"
    )

    conn.execute(
        """
        INSERT OR IGNORE INTO security_evidence (
            isin,
            source_name,
            source_type,
            result_status,
            source_url,
            evidence_summary,
            supports_russian_nexus,
            retrieved_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            isin,
            "GLEIF",
            "ISIN_TO_LEI",
            "MATCHED",
            response_url,
            evidence_summary,
            supports_russian_nexus,
            retrieved_at,
        ),
    )

    # CONFIRMED案件不允許被單一GLEIF查詢結果覆蓋
    conn.execute(
        """
        INSERT INTO security_risk_assessment (
            isin,
            issuer_name,
            issuer_country,
            classification,
            confidence,
            review_status,
            updated_at,
            notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(isin) DO UPDATE SET
            issuer_name = excluded.issuer_name,
            issuer_country = excluded.issuer_country,
            classification = excluded.classification,
            confidence = excluded.confidence,
            review_status = excluded.review_status,
            updated_at = excluded.updated_at,
            notes = excluded.notes
        WHERE security_risk_assessment.review_status != 'CONFIRMED'
        """,
        (
            isin,
            issuer_name,
            issuer_country,
            classification,
            confidence,
            "PENDING_REVIEW",
            retrieved_at,
            note,
        ),
    )

    return lei, issuer_name, issuer_country, classification


def main():
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(f"找不到資料庫：{DATABASE_PATH}")

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    try:
        isin = validate_isin(input("請輸入12碼ISIN："))
    except ValueError as error:
        print(f"輸入錯誤：{error}")
        return

    print(f"正在向GLEIF查詢：{isin}")

    try:
        response = requests.get(
            GLEIF_API_URL,
            params={"filter[isin]": isin},
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        print(f"GLEIF查詢失敗：{error}")
        return

    payload = response.json()
    records = payload.get("data", [])
    retrieved_at = datetime.now().isoformat(timespec="seconds")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_file = RAW_DIR / f"gleif_{isin}_{timestamp}.json"

    with raw_file.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)

    with sqlite3.connect(DATABASE_PATH) as conn:
        if not records:
            save_not_mapped(
                conn,
                isin,
                response.url,
                raw_file,
                retrieved_at,
            )

            print("查詢結果數量：0")
            print(f"原始回應：{raw_file}")
            print("GLEIF沒有此ISIN的對應資料。")
            print("已記錄GLEIF查無對應資料的證據；既有確認結果不會被覆蓋。")
        else:
            print(f"查詢結果數量：{len(records)}")

            for record in records:
                lei, issuer, country, classification = save_gleif_match(
                    conn,
                    isin,
                    record,
                    response.url,
                    raw_file,
                    retrieved_at,
                )

                print(f"LEI：{lei}")
                print(f"法人名稱：{issuer}")
                print(f"國家：{country or 'UNKNOWN'}")
                print(f"初步分類：{classification}")

            print(f"原始回應：{raw_file}")

        current = conn.execute(
            """
            SELECT
                classification,
                confidence,
                review_status
            FROM security_risk_assessment
            WHERE isin = ?
            """,
            (isin,),
        ).fetchone()

    if current:
        print("\n資料庫目前判定")
        print("=" * 40)
        print(f"分類：{current[0]}")
        print(f"信心：{current[1]}")
        print(f"審查狀態：{current[2]}")


if __name__ == "__main__":
    main()