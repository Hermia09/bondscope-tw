import sqlite3
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = PROJECT_ROOT / "data" / "bondscope.db"


def query_bond(isin: str):
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.row_factory = sqlite3.Row

        bond = connection.execute(
            """
            SELECT
                bond_code,
                isin,
                bond_name,
                bond_short_name,
                currency,
                issue_date,
                maturity_date,
                coupon_rate,
                rate_type,
                redemption_method,
                source_date
            FROM bonds
            WHERE isin = ?
            """,
            (isin,),
        ).fetchone()

        if bond is None:
            return None, []

        cashflows = connection.execute(
            """
            SELECT
                payment_sequence,
                scheduled_payment_date,
                actual_payment_date,
                interest_amount,
                principal_amount
            FROM cashflow_events
            WHERE bond_code = ?
              AND scheduled_payment_date >= ?
            ORDER BY scheduled_payment_date
            """,
            (bond["bond_code"], date.today().isoformat()),
        ).fetchall()

        return bond, cashflows


def main():
    isin = input("請輸入12碼 ISIN：").strip().upper()

    if len(isin) != 12:
        print("ISIN格式錯誤：必須是12碼。")
        return

    bond, cashflows = query_bond(isin)

    if bond is None:
        print("資料庫中找不到這組 ISIN。")
        return

    print("\n債券基本資料")
    print("=" * 40)
    print(f"債券名稱：{bond['bond_name']}")
    print(f"債券代號：{bond['bond_code']}")
    print(f"ISIN：{bond['isin']}")
    print(f"幣別：{bond['currency']}")
    print(f"發行日：{bond['issue_date']}")
    print(f"到期日：{bond['maturity_date']}")
    print(f"票面利率：{bond['coupon_rate']}%")
    print(f"利率別：{bond['rate_type']}")
    print(f"還本方式：{bond['redemption_method']}")
    print(f"資料日期：{bond['source_date']}")

    print("\n未來還本付息")
    print("=" * 40)

    if not cashflows:
        print("找不到未來還本付息資料。")
        return

    for cashflow in cashflows:
        print(
            f"{cashflow['scheduled_payment_date']}｜"
            f"期次 {cashflow['payment_sequence']}｜"
            f"利息 {cashflow['interest_amount']:,.2f}｜"
            f"本金 {cashflow['principal_amount']:,.2f}"
        )


if __name__ == "__main__":
    main()