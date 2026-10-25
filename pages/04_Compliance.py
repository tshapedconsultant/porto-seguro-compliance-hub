from __future__ import annotations



import json

from pathlib import Path



import streamlit as st



from utils.compliance_audit import (

    COMPLIANCE_REPORT_PATH,

    bias_audit_to_dataframe,

    load_saved_audit_results,

    run_full_compliance_audit,

)

from utils.data_loaders import (

    audit_results_mtime,

    load_bias_audit_results,

    load_compliance_status,

)



st.header("🇪🇺 Regulatory Compliance & EU AI Act Hub")

st.info(

    "Command center for validating High-Risk AI systems under the EU AI Act and Solvency II. "
    "GDPR Art. 35 EIPD: sidebar **DPIA GDPR** (`gdpr_dpia_v1.json`) — demonstration pack, not an AEPD filing."

)



compliance_status = load_compliance_status(audit_results_mtime())

saved_audit = load_saved_audit_results()

bias_audit = load_bias_audit_results()



if compliance_status.get("audit_pending", True):

    st.warning(

        "⚠️ **Audit pending.** Click **Run full audit** to generate "

        "`docs/audit_results.json`."

    )



tab1, tab3, tab4 = st.tabs(

    [

        "📊 General Status",

        "🔍 Bias & Fairness Audit",

        "📄 Conformity Declaration",

    ]

)



with tab1:

    overall = compliance_status.get("overall", "⚠️ Not Audited")

    if "✅" in overall:

        st.success(f"**Overall Compliance Status: {overall}**")

    elif "⚠️" in overall:

        st.warning(f"**Overall Compliance Status: {overall}**")

    else:

        st.error(f"**Overall Compliance Status: {overall}**")



    if compliance_status.get("last_audit"):

        st.caption(f"Last audit timestamp: {compliance_status['last_audit']}")



    if st.button("🔄 Run full audit", type="primary"):

        with st.spinner("Running compliance audit..."):

            try:

                run_full_compliance_audit(sample_size=10000)

                load_compliance_status.clear()

                load_bias_audit_results.clear()

                st.success("Audit saved to `docs/audit_results.json`.")

                st.rerun()

            except Exception as exc:

                st.error(f"Audit error: {exc}")



    st.markdown("---")

    col1, col2, col3 = st.columns(3)

    col1.metric(

        "Solvency II",

        compliance_status.get("solvency_ii", "N/A").replace("✅", "Pass").replace("⚠️", "Warn"),

    )

    col2.metric(

        "EU AI Act",

        compliance_status.get("eu_ai_act", "N/A").replace("✅", "Pass").replace("⚠️", "Warn"),

    )

    col3.metric(

        "Responsible AI",

        compliance_status.get("responsible_ai", "N/A").replace("✅", "Pass").replace("⚠️", "Warn"),

    )



    st.info(

        "📋 See the detailed Article-by-Article mapping and Solvency II crosswalk on "

        "the **⚖️ EU AI Act** page in the sidebar."

    )



    st.markdown("#### Responsible AI Pillars")

    p1, p2, p3, p4, p5 = st.columns(5)

    p1.metric("Fairness", compliance_status.get("fairness", "N/A"))

    p2.metric("Transparency", compliance_status.get("transparency", "N/A"))

    p3.metric("Accountability", compliance_status.get("accountability", "N/A"))

    p4.metric("Robustness", compliance_status.get("robustness", "N/A"))

    p5.metric("Monitoring (Art. 9)", compliance_status.get("monitoring", "N/A"))



with tab3:

    st.subheader("Demographic Parity & Equalized Odds")

    st.info(

        "Porto Seguro does not publish age/gender. The audit uses **proxies** from "

        "anonymized features and the model's **optimal threshold**."

    )



    if bias_audit:

        if bias_audit.get("note"):

            st.caption(bias_audit["note"])

        if bias_audit.get("classification_threshold"):

            st.caption(

                f"Classification threshold: **{bias_audit['classification_threshold']:.4f}**"

            )

        st.dataframe(bias_audit_to_dataframe(bias_audit), use_container_width=True, hide_index=True)

        if bias_audit.get("error"):

            st.error(bias_audit["error"])

        elif bias_audit.get("audit_valid") is False:

            st.error(

                "⚠️ **Invalid audit:** all metrics at 0.000 do not mean fairness — "

                "they indicate the model produced no positive predictions (misaligned artifacts or wrong threshold). "

                "Run `python run_training.py` and audit again."

            )

        elif bias_audit.get("overall_compliance"):

            st.success("✅ Demographic parity and equalized odds within thresholds (Δ ≤ 10%).")

        else:

            st.warning("⚠️ Deviations across proxy groups — review before production.")

    else:

        st.dataframe(bias_audit_to_dataframe({}), use_container_width=True, hide_index=True)



    if st.button("▶️ Run Full Bias Audit"):

        with st.spinner("Audit in progress..."):

            try:

                run_full_compliance_audit(sample_size=10000)

                load_compliance_status.clear()

                load_bias_audit_results.clear()

                st.rerun()

            except Exception as exc:

                st.error(f"Error: {exc}")



with tab4:

    st.subheader("Legal Evidence Export")

    st.write("Generate the EU Conformity Declaration from artifacts and the latest audit.")



    if st.button("📄 Generate Conformity Declaration"):

        try:

            payload = saved_audit

            if not payload:

                payload = run_full_compliance_audit(sample_size=10000)

                load_compliance_status.clear()

                load_bias_audit_results.clear()



            report_doc = payload.get("conformity_report") if payload else None

            if not report_doc and COMPLIANCE_REPORT_PATH.exists():

                report_doc = json.loads(

                    COMPLIANCE_REPORT_PATH.read_text(encoding="utf-8")

                )

            if not report_doc:

                raise FileNotFoundError("Run the full audit first.")



            st.success("Document generated. Ready for Compliance Officer review.")

            st.download_button(

                label="⬇️ Download Conformity Declaration (JSON)",

                data=json.dumps(report_doc, indent=2, ensure_ascii=False),

                file_name="eu_ai_act_conformity_v1.json",

                mime="application/json",

            )

        except Exception as exc:

            st.error(f"Could not generate report: {exc}")



    if COMPLIANCE_REPORT_PATH.exists():

        st.caption(f"Latest report on disk: `{COMPLIANCE_REPORT_PATH}`")

