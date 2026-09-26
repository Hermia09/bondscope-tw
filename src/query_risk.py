import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = PROJECT_ROOT / "data" / "bondscope.db"


def main():
    isin = input("請輸入12碼ISIN：").strip().upper()

    if len(isin) != 12 or not isin.isalnum():
        print("ISIN格式不正確。")
        return

    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.row_factory = sqlite3.Row

        assessment = conn.execute(
            """
            SELECT
                isin,
                issuer_name,
                issuer_country,
                classification,
                confidence,
                review_status,
                updated_at,
                notes
            FROM security_risk_assessment
            WHERE isin = ?
            """,
            (isin,),
        ).fetchone()

        evidence = conn.execute(
            """
            SELECT
                source_name,
                source_type,
                result_status,
                source_url,
                evidence_summary,
                supports_russian_nexus,
                retrieved_at
            FROM security_evidence
            WHERE isin = ?
            ORDER BY retrieved_at DESC
            """,
            (isin,),
        ).fetchall()

    print("\n風險判定")
    print("=" * 60)

    if assessment is None:
        print("尚未建立此ISIN的風險判定。")
        print("請先執行：python src\\gleif_client.py")
        return

    print(f"ISIN：{assessment['isin']}")
    print(f"發行人：{assessment['issuer_name'] or '尚未辨識'}")
    print(f"發行人國家：{assessment['issuer_country'] or '尚未辨識'}")
    print(f"分類：{assessment['classification']}")
    print(f"信心等級：{assessment['confidence']}")
    print(f"審查狀態：{assessment['review_status']}")
    print(f"更新時間：{assessment['updated_at']}")
    print(f"備註：{assessment['notes'] or '無'}")

    print("\n判定證據")
    print("=" * 60)

    if not evidence:
        print("目前沒有來源證據。")
        return

    for number, row in enumerate(evidence, start=1):
        support = row["supports_russian_nexus"]

        if support == 1:
            support_text = "支持俄羅斯關聯"
        elif support == 0:
            support_text = "未發現俄羅斯關聯，但不足以排除"
        else:
            support_text = "無法判斷"

        print(f"\n證據 {number}")
        print(f"來源：{row['source_name']}")
        print(f"類型：{row['source_type']}")
        print(f"結果：{row['result_status']}")
        print(f"俄羅斯關聯：{support_text}")
        print(f"內容：{row['evidence_summary'] or '無'}")
        print(f"網址：{row['source_url'] or '無'}")
        print(f"取得時間：{row['retrieved_at']}")


if __name__ == "__main__":
    main()