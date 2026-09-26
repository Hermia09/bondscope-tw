import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parent
DATABASE_PATH = PROJECT_ROOT / "data" / "bondscope.db"


st.set_page_config(
    page_title="BondScope TW",
    page_icon="🔎",
    layout="wide",
)


@st.cache_data(ttl=300)
def query_bond(isin: str):
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.row_factory = sqlite3.Row

        bond_row = connection.execute(
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
                registrar,
                paying_agent,
                source_date
            FROM bonds
            WHERE isin = ?
            """,
            (isin,),
        ).fetchone()

        if bond_row is None:
            return None, pd.DataFrame()

        bond = dict(bond_row)

        cashflows = pd.read_sql_query(
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
            connection,
            params=(
                bond["bond_code"],
                date.today().isoformat(),
            ),
        )

        return bond, cashflows


st.title("BondScope TW")
st.caption("臺灣債券基本資料與還本付息查詢")

if not DATABASE_PATH.exists():
    st.error("找不到 SQLite 資料庫，請先執行 build_database.py。")
    st.stop()

with st.form("bond_search"):
    isin_input = st.text_input(
        "請輸入12碼 ISIN",
        placeholder="例如：TW000B201607",
    )

    submitted = st.form_submit_button("查詢債券")

if submitted:
    isin = isin_input.strip().upper()

    if len(isin) != 12 or not isin.isalnum():
        st.error("ISIN格式錯誤，請輸入12碼英文字母或數字。")
    else:
        bond, cashflows = query_bond(isin)

        if bond is None:
            st.warning("資料庫中找不到這組 ISIN。")
        else:
            st.subheader(bond["bond_name"])

            coupon_rate = bond["coupon_rate"]
            coupon_display = (
                f"{coupon_rate:g}%"
                if coupon_rate is not None
                else "資料不足"
            )

            column1, column2, column3 = st.columns(3)

            column1.metric("票面利率", coupon_display)
            column2.metric("到期日", bond["maturity_date"])
            column3.metric("計價幣別", bond["currency"])

            st.markdown("#### 債券基本資料")

            bond_details = pd.DataFrame(
                {
                    "欄位": [
                        "ISIN",
                        "債券代號",
                        "債券簡稱",
                        "發行日",
                        "利率別",
                        "還本方式",
                        "登錄機構",
                        "本息兌領機構",
                        "資料日期",
                    ],
                    "內容": [
                        bond["isin"],
                        bond["bond_code"],
                        bond["bond_short_name"],
                        bond["issue_date"],
                        bond["rate_type"],
                        bond["redemption_method"],
                        bond["registrar"],
                        bond["paying_agent"],
                        bond["source_date"],
                    ],
                }
            )

            st.dataframe(
                bond_details,
                hide_index=True,
            )

            st.markdown("#### 未來還本付息")

            if cashflows.empty:
                st.info("找不到未來還本付息資料。")
            else:
                total_interest = cashflows[
                    "interest_amount"
                ].fillna(0).sum()

                total_principal = cashflows[
                    "principal_amount"
                ].fillna(0).sum()

                summary1, summary2 = st.columns(2)

                summary1.metric(
                    "未來利息合計",
                    f"{bond['currency']} {total_interest:,.2f}",
                )

                summary2.metric(
                    "未來本金合計",
                    f"{bond['currency']} {total_principal:,.2f}",
                )

                display_cashflows = cashflows.rename(
                    columns={
                        "payment_sequence": "期次",
                        "scheduled_payment_date": "預定付款日",
                        "actual_payment_date": "實際付款日",
                        "interest_amount": "利息金額",
                        "principal_amount": "本金金額",
                    }
                )

                st.dataframe(
                    display_cashflows,
                    hide_index=True,
                )

            st.caption(
                "資料來源：臺灣集中保管結算所 OpenAPI｜"
                f"資料日期：{bond['source_date']}"
            )

            st.info(
                "本網站內容僅供資料查詢與研究參考，"
                "不構成任何投資建議。"
            )