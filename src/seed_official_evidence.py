import sqlite3
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = PROJECT_ROOT / "data" / "bondscope.db"

ISIN = "XS0088543193"


def main():
    retrieved_at = datetime.now().isoformat(timespec="seconds")

    evidence_rows = [
        (
            ISIN,
            "Luxembourg Stock Exchange",
            "OFFICIAL_EXCHANGE",
            "MATCHED",
            "https://www.luxse.com/security/XS0088543193/29036",
            (
                "LuxSE將此債券列為RussianFed 12.75%，"
                "到期日為2028-06-24。"
            ),
            1,
            retrieved_at,
        ),
        (
            ISIN,
            "Moscow Exchange",
            "OFFICIAL_EXCHANGE",
            "MATCHED",
            "https://www.moex.com/en/issue.aspx?code=XS0088543193",
            (
                "MOEX將此債券列為Finance Ministry of Russia eurobond。"
            ),
            1,
            retrieved_at,
        ),
        (
            ISIN,
            "Clearstream",
            "CLEARING_NOTICE",
            "MATCHED",
            (
                "https://www.clearstream.com/clearstream-en/"
                "res-library/settlement/a25006-4260720"
            ),
            (
                "Clearstream俄羅斯主權Eurobond替換公告包含此ISIN。"
            ),
            1,
            retrieved_at,
        ),
    ]

    with sqlite3.connect(DATABASE_PATH) as conn:
        # 移除初始化程式寫入的模擬GLEIF證據。
        # 真正由gleif_client.py取得、包含原始檔名的紀錄會保留。
        deleted = conn.execute(
            """
            DELETE FROM security_evidence
            WHERE source_name = 'GLEIF'
              AND evidence_summary = 'GLEIF API 查詢結果為 0 筆。'
            """
        ).rowcount

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
            evidence_rows,
        )

        evidence_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM security_evidence
            WHERE isin = ?
            """,
            (ISIN,),
        ).fetchone()[0]

    print("官方證據匯入完成")
    print(f"移除初始化模擬紀錄：{deleted} 筆")
    print(f"{ISIN} 目前證據數量：{evidence_count} 筆")


if __name__ == "__main__":
    main()