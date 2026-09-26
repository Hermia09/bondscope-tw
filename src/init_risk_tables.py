from pathlib import Path
import sqlite3
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = PROJECT_ROOT / "data" / "bondscope.db"


def main():
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(f"找不到資料庫：{DATABASE_PATH}")

    updated_at = datetime.now().isoformat(timespec="seconds")

    with sqlite3.connect(DATABASE_PATH) as conn:
        # 每一個 ISIN 的最新風險判定
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS security_risk_assessment (
                isin TEXT PRIMARY KEY,
                issuer_name TEXT,
                issuer_country TEXT,
                classification TEXT NOT NULL,
                confidence TEXT NOT NULL,
                review_status TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                notes TEXT
            )
            """
        )

        # 每個判定背後使用的資料來源與證據
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS security_evidence (
                evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                isin TEXT NOT NULL,
                source_name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                result_status TEXT NOT NULL,
                source_url TEXT,
                evidence_summary TEXT,
                supports_russian_nexus INTEGER,
                retrieved_at TEXT NOT NULL,
                UNIQUE (
                    isin,
                    source_name,
                    result_status,
                    evidence_summary
                )
            )
            """
        )

        assessments = [
            (
                "XS0088543193",
                "Russian Federation",
                "RU",
                "RUSSIAN_SOVEREIGN",
                "HIGH",
                "CONFIRMED",
                updated_at,
                "GLEIF 無對應，但官方交易所資料可辨識為俄羅斯聯邦債券。",
            ),
            (
                "XS1636270634",
                None,
                None,
                "INSUFFICIENT_DATA",
                "LOW",
                "PENDING_REVIEW",
                updated_at,
                "GLEIF 查無 ISIN 對應資料，仍需查詢其他來源。",
            ),
            (
                "XS2363250833",
                None,
                None,
                "INSUFFICIENT_DATA",
                "LOW",
                "PENDING_REVIEW",
                updated_at,
                "GLEIF 查無 ISIN 對應資料，仍需查詢其他來源。",
            ),
        ]

        conn.executemany(
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
            """,
            assessments,
        )

        gleif_evidence = [
            (
                "XS1636270634",
                "GLEIF",
                "ISIN_TO_LEI",
                "NOT_MAPPED",
                "https://api.gleif.org/api/v1/lei-records",
                "GLEIF API 查詢結果為 0 筆。",
                None,
                updated_at,
            ),
            (
                "XS0088543193",
                "GLEIF",
                "ISIN_TO_LEI",
                "NOT_MAPPED",
                "https://api.gleif.org/api/v1/lei-records",
                "GLEIF API 查詢結果為 0 筆。",
                None,
                updated_at,
            ),
            (
                "XS2363250833",
                "GLEIF",
                "ISIN_TO_LEI",
                "NOT_MAPPED",
                "https://api.gleif.org/api/v1/lei-records",
                "GLEIF API 查詢結果為 0 筆。",
                None,
                updated_at,
            ),
        ]

        conn.executemany(
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
            gleif_evidence,
        )

        assessment_count = conn.execute(
            "SELECT COUNT(*) FROM security_risk_assessment"
        ).fetchone()[0]

        evidence_count = conn.execute(
            "SELECT COUNT(*) FROM security_evidence"
        ).fetchone()[0]

    print("風險判定資料表建立成功")
    print(f"資料庫位置：{DATABASE_PATH}")
    print(f"風險判定筆數：{assessment_count}")
    print(f"來源證據筆數：{evidence_count}")


if __name__ == "__main__":
    main()