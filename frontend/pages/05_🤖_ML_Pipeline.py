"""ML pipeline page: feature explorer, training, model registry."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import plotly.graph_objects as go
import streamlit as st

from blackorca.data.catalog import Catalog
from blackorca.ml.models import ModelRegistry
from blackorca.ml.pipelines import PITPipeline
from blackorca.ml.train import train_model
from blackorca.runs.registry import record
from blackorca.strategies.examples.ml_signal import default_feature_stack
from frontend.components.common import PLOTLY_TEMPLATE, init_page

init_page("ML Pipeline", icon="🤖")
st.title("🤖 ML Pipeline")

cat = Catalog()
reg = ModelRegistry()
instruments = cat.list_instruments()

tab_feat, tab_train, tab_models = st.tabs(["Feature explorer", "Train", "Registry"])

# ---------------------------------------------------------------------------
# Feature explorer
# ---------------------------------------------------------------------------

with tab_feat:
    if not instruments:
        st.info("Ingest data first.")
    else:
        c1, c2 = st.columns(2)
        sym = c1.selectbox("Symbol", instruments, key="ml_feat_sym")
        feature = c2.selectbox(
            "Feature",
            ["ret_1d", "ret_5d", "realvol_20d", "momz_20d", "adv_ratio_20d", "overnight_gap", "intraday_range"],
        )
        if st.button("Compute"):
            df = cat.read_bars([sym], date(2000, 1, 1), date.today())
            pipeline = PITPipeline(default_feature_stack())
            feats = pipeline.transform(df).drop_nulls(feature)
            if feature not in feats.columns:
                st.error(f"Feature {feature} not in stack — pick another.")
            else:
                fig = go.Figure(
                    go.Scatter(
                        x=feats["as_of"].to_list(),
                        y=feats[feature].to_list(),
                        line=dict(color="#7dd3fc"),
                    )
                )
                fig.update_layout(template=PLOTLY_TEMPLATE, height=380, margin=dict(l=10, r=10, t=20, b=10), title=feature)
                st.plotly_chart(fig, use_container_width=True)
                # Distribution
                fig2 = go.Figure(go.Histogram(x=feats[feature].to_list(), nbinsx=60, marker_color="#7dd3fc"))
                fig2.update_layout(template=PLOTLY_TEMPLATE, height=280, margin=dict(l=10, r=10, t=20, b=10), title=f"Distribution of {feature}")
                st.plotly_chart(fig2, use_container_width=True)

# ---------------------------------------------------------------------------
# Train
# ---------------------------------------------------------------------------

with tab_train:
    if not instruments:
        st.info("Ingest data first.")
    else:
        with st.form("train_form"):
            c1, c2, c3 = st.columns(3)
            sym = c1.selectbox("Symbol", instruments, key="ml_train_sym")
            framework = c2.selectbox("Framework", ["lightgbm", "ridge"])
            years = c3.number_input("Years", 1, 15, 4)
            c4, c5, c6 = st.columns(3)
            horizon = c4.number_input("Target horizon (days)", 1, 30, 1)
            splits = c5.number_input("Walk-forward splits", 2, 10, 5)
            name = c6.text_input("Model name", value=f"{sym.lower()}_demo")
            submitted = st.form_submit_button("Train", use_container_width=True)
        if submitted:
            started = datetime.now(timezone.utc)
            end = date.today()
            start = end - timedelta(days=int(years) * 365)
            df = cat.read_bars([sym], start, end)
            if df.is_empty():
                st.error("No bars; ingest first.")
            else:
                pipeline = PITPipeline(default_feature_stack())
                try:
                    res = train_model(
                        df,
                        pipeline,
                        name=name,
                        framework=framework,
                        target_horizon=int(horizon),
                        n_splits=int(splits),
                    )
                    c1, c2, c3 = st.columns(3)
                    c1.metric("CV IC (mean)", f"{res.cv_metrics['cv_ic_mean']:.4f}")
                    c2.metric("CV IC (std)", f"{res.cv_metrics['cv_ic_std']:.4f}")
                    c3.metric("Train rows", res.n_train_rows)
                    st.success(f"Saved model **{res.model_name}** version `{res.version}`")
                    record(
                        kind="training",
                        name=f"{res.model_name}/{res.version}",
                        started_at=started,
                        payload={
                            "framework": framework,
                            "cv_metrics": res.cv_metrics,
                            "features": res.feature_columns,
                        },
                    )
                except Exception as e:
                    st.error(f"Training failed: {e}")
                    record(kind="training", name=name, started_at=started, error=str(e))

# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

with tab_models:
    listing = reg.list()
    if not listing:
        st.info("No models yet.")
    else:
        for model_name, versions in listing.items():
            with st.expander(f"**{model_name}** ({len(versions)} versions)"):
                for v in versions:
                    _, meta = reg.load(model_name, v)
                    cols = st.columns([1, 1, 1, 2])
                    cols[0].write(v)
                    cols[1].write(meta.framework)
                    cols[2].write(f"IC: {meta.metrics.get('cv_ic_mean', 0):.4f}")
                    cols[3].write(", ".join(meta.features[:6]) + ("…" if len(meta.features) > 6 else ""))
