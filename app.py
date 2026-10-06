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
def query_security(isin: str):
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

        bond = dict(bond_row) if bond_row else None

        if bond:
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
        else:
            cashflows = pd.DataFrame()

        risk_row = connection.execute(
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

        risk = dict(risk_row) if risk_row else None

        evidence = pd.read_sql_query(
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
            ORDER BY
                supports_russian_nexus DESC,
                retrieved_at DESC
            """,
            connection,
            params=(isin,),
        )

        return bond, cashflows, risk, evidence


def display_risk_assessment(risk, evidence):
    st.markdown("### 發行人與俄羅斯關聯風險")

    if risk is None:
        st.warning(
            "尚未建立此 ISIN 的發行人風險判定。"
            "請先執行 GLEIF 查詢並進行來源查證。"
        )
        return

    classification = risk["classification"]

    classification_labels = {
        "RUSSIAN_SOVEREIGN": "俄羅斯主權債",
        "RUSSIAN_CORPORATE": "俄羅斯企業債",
        "POTENTIAL_RUSSIAN_NEXUS": "可能具有俄羅斯關聯",
        "INSUFFICIENT_DATA": "資料不足",
        "ISSUER_IDENTIFIED": "已辨識發行人，仍待風險審查",
        "NON_RUSSIAN": "未發現俄羅斯關聯",
    }

    classification_display = classification_labels.get(
        classification,
        classification,
    )

    if classification in {
        "RUSSIAN_SOVEREIGN",
        "RUSSIAN_CORPORATE",
    }:
        st.error(
            "🚨 俄羅斯相關債券警示\n\n"
            "建議通知前台業務單位，並向保管銀行確認"
            "款項、清算及國際清算機構目前處理狀態。"
        )
    elif classification == "POTENTIAL_RUSSIAN_NEXUS":
        st.warning(
            "⚠️ 此債券可能具有俄羅斯關聯，"
            "目前仍需要其他官方來源確認。"
        )
    elif classification == "INSUFFICIENT_DATA":
        st.warning(
            "⚠️ 目前資料不足，不能判定此債券是否具有俄羅斯關聯。"
        )
    elif classification == "NON_RUSSIAN":
        st.success("目前來源未發現俄羅斯關聯。")
    else:
        st.info("已辨識部分發行人資料，但尚未完成風險分類。")

    risk1, risk2, risk3 = st.columns(3)

    risk1.metric(
        "風險分類",
        classification_display,
    )
    risk2.metric(
        "信心等級",
        risk["confidence"],
    )
    risk3.metric(
        "審查狀態",
        risk["review_status"],
    )

    risk_details = pd.DataFrame(
        {
            "欄位": [
                "發行人",
                "發行人國家",
                "更新時間",
                "判定備註",
            ],
            "內容": [
                risk["issuer_name"] or "尚未辨識",
                risk["issuer_country"] or "尚未辨識",
                risk["updated_at"],
                risk["notes"] or "無",
            ],
        }
    )

    st.dataframe(
        risk_details,
        hide_index=True,
        use_container_width=True,
    )

    with st.expander(
        f"查看判定證據（{len(evidence)} 筆）",
        expanded=True,
    ):
        if evidence.empty:
            st.info("目前沒有保存任何判定證據。")
        else:
            for number, row in enumerate(
                evidence.to_dict("records"),
                start=1,
            ):
                support = row["supports_russian_nexus"]

                if support == 1:
                    support_text = "🔴 支持俄羅斯關聯"
                elif support == 0:
                    support_text = "🟢 未發現俄羅斯關聯"
                else:
                    support_text = "⚪ 無法判斷"

                st.markdown(
                    f"**證據 {number}｜{row['source_name']}**"
                )
                st.write(
                    f"{support_text}｜"
                    f"{row['source_type']}｜"
                    f"{row['result_status']}"
                )
                st.write(row["evidence_summary"] or "沒有摘要")

                if row["source_url"]:
                    st.markdown(
                        f"[開啟官方來源]({row['source_url']})"
                    )

                st.caption(
                    f"資料取得時間：{row['retrieved_at']}"
                )

                if number < len(evidence):
                    st.divider()

    st.caption(
        "風險分類僅供作業監控與人工複核，"
        "不構成制裁法令或法律意見。"
    )


def display_bond_information(bond, cashflows):
    st.markdown("### TDCC 債券資料")

    if bond is None:
        st.warning(
            "TDCC 債券主檔中找不到這組 ISIN，"
            "但仍可查看上方的發行人風險判定。"
        )
        return

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
        use_container_width=True,
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
            use_container_width=True,
        )

    st.caption(
        "資料來源：臺灣集中保管結算所 OpenAPI｜"
        f"資料日期：{bond['source_date']}"
    )


st.title("BondScope TW")
st.caption("臺灣債券現金流與發行人風險查詢")

if not DATABASE_PATH.exists():
    st.error("找不到 SQLite 資料庫，請先建立資料庫。")
    st.stop()

with st.form("bond_search"):
    isin_input = st.text_input(
        "請輸入12碼 ISIN",
        placeholder="例如：TW000B201607 或 XS0088543193",
    )

    submitted = st.form_submit_button("查詢債券")

if submitted:
    isin = isin_input.strip().upper()

    if len(isin) != 12 or not isin.isalnum():
        st.error("ISIN格式錯誤，請輸入12碼英文字母或數字。")
    else:
        bond, cashflows, risk, evidence = query_security(isin)

        if bond is None and risk is None:
            st.warning(
                "TDCC及風險資料庫中都找不到這組 ISIN。"
            )
        else:
            display_risk_assessment(risk, evidence)
            st.divider()
            display_bond_information(bond, cashflows)

            st.info(
                "本網站內容僅供資料查詢、作業監控與研究參考，"
                "不構成任何投資或法律建議。"
            )