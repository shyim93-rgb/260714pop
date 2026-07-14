import re
import glob
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

# ----------------------------------------------------------------------------
# 기본 설정
# ----------------------------------------------------------------------------
st.set_page_config(page_title="연령별 인구 구조 탐색기", page_icon="📊", layout="wide")

st.title("📊 연령별 인구 구조 탐색기")
st.caption("행정안전부 『연령별 인구현황』 데이터를 기반으로 지역별 인구 구조를 살펴보고, "
            "인구 구조가 가장 비슷한 '쌍둥이 지역'을 찾아드립니다.")


# ----------------------------------------------------------------------------
# 데이터 로드
# ----------------------------------------------------------------------------
@st.cache_data
def load_data():
    # main.py와 같은 폴더에 있는 '연령별인구현황' CSV 파일을 자동으로 찾습니다.
    candidates = glob.glob("*연령별인구현황*.csv")
    if not candidates:
        candidates = glob.glob("*.csv")
    if not candidates:
        raise FileNotFoundError("같은 폴더에서 CSV 데이터 파일을 찾을 수 없습니다.")

    file_path = candidates[0]

    # 행정안전부 데이터는 보통 CP949(EUC-KR) 인코딩입니다.
    for enc in ["cp949", "euc-kr", "utf-8-sig"]:
        try:
            df = pd.read_csv(file_path, encoding=enc, thousands=",")
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    else:
        raise UnicodeDecodeError("CSV 인코딩을 확인해주세요 (cp949 / euc-kr / utf-8 시도).")

    # 지역명 정리: "서울특별시  (1100000000)" -> "서울특별시"
    df["행정구역"] = df["행정구역"].astype(str).str.replace(r"\s*\(\d+\)", "", regex=True).str.strip()

    # 연-월 접두어 자동 탐지 (예: "2026년06월_")
    prefix_match = re.search(r"(\d{4}년\d{2}월)_", df.columns[1])
    prefix = prefix_match.group(1) if prefix_match else None

    return df, file_path, prefix


try:
    df, file_path, prefix = load_data()
except Exception as e:
    st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {e}")
    st.stop()

st.success(f"데이터 로드 완료: `{file_path}` (기준월: {prefix.replace('년', '년 ').replace('월','월') if prefix else '알 수 없음'})")


# ----------------------------------------------------------------------------
# 연령 컬럼 파싱 유틸
# ----------------------------------------------------------------------------
def age_columns(gender: str):
    """gender: '계' / '남' / '여' 에 해당하는 연령별 컬럼명과 나이(정수) 리스트를 반환"""
    pat = re.compile(rf"^{re.escape(prefix)}_{gender}_(\d+|100세 이상)세?$")
    cols, ages = [], []
    for c in df.columns:
        # 원본은 "..._0세", "..._100세 이상" 형태
        if c.startswith(f"{prefix}_{gender}_") and ("세" in c) and ("총인구수" not in c) and ("연령구간인구수" not in c):
            m = re.search(r"(\d+)세(?!\s*이상)$|(\d+)세\s*이상$", c)
            if m:
                age_val = int(m.group(1)) if m.group(1) else int(m.group(2))
                cols.append(c)
                ages.append(age_val)
    # 나이 순으로 정렬
    order = np.argsort(ages)
    cols = [cols[i] for i in order]
    ages = [ages[i] for i in order]
    return cols, ages


cols_total, ages = age_columns("계")
cols_male, _ = age_columns("남")
cols_female, _ = age_columns("여")

age_labels = [f"{a}세" if a < 100 else "100세+" for a in ages]

regions_all = df["행정구역"].tolist()
regions_no_national = [r for r in regions_all if r != "전국"]


def get_counts(region: str, cols: list):
    row = df.loc[df["행정구역"] == region, cols]
    return row.values.flatten().astype(float)


def get_proportion(region: str, cols: list):
    counts = get_counts(region, cols)
    total = counts.sum()
    return counts / total if total > 0 else counts


# ----------------------------------------------------------------------------
# 탭 구성
# ----------------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs(["🗺️ 지역별 인구 구조 비교", "🧍 인구 피라미드", "👯 쌍둥이 지역 찾기"])

# ----------------------------------------------------------------------------
# TAB 1. 지역별 인구 구조 비교 (여러 지역 겹쳐보기)
# ----------------------------------------------------------------------------
with tab1:
    st.subheader("여러 지역의 연령별 인구 비율 비교")

    col_a, col_b = st.columns([2, 1])
    with col_a:
        selected_regions = st.multiselect(
            "비교할 지역을 선택하세요 (여러 개 선택 가능)",
            options=regions_all,
            default=["전국", "서울특별시", "세종특별자치시"] if "세종특별자치시" in regions_all else regions_all[:3],
        )
    with col_b:
        gender_choice = st.radio("성별", ["계", "남", "여"], horizontal=True)
        show_pct = st.checkbox("비율(%)로 보기", value=True)

    gender_cols_map = {"계": cols_total, "남": cols_male, "여": cols_female}
    target_cols = gender_cols_map[gender_choice]

    if selected_regions:
        fig = go.Figure()
        for region in selected_regions:
            if show_pct:
                y_vals = get_proportion(region, target_cols) * 100
                y_title = "인구 비율 (%)"
            else:
                y_vals = get_counts(region, target_cols)
                y_title = "인구 수 (명)"

            fig.add_trace(go.Scatter(
                x=age_labels,
                y=y_vals,
                mode="lines",
                name=region,
                line=dict(width=2.5, shape="spline", smoothing=0.3),
                hovertemplate="%{x}<br>" + region + ": %{y:.3f}" + ("%" if show_pct else "명") + "<extra></extra>",
            ))

        fig.update_layout(
            height=560,
            xaxis_title="연령",
            yaxis_title=y_title,
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            xaxis=dict(rangeslider=dict(visible=True), type="category"),
            template="plotly_white",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("💡 하단의 범위 슬라이더로 특정 연령대를 확대해서 볼 수 있어요. 범례를 클릭하면 해당 지역을 숨길 수 있습니다.")
    else:
        st.info("비교할 지역을 1개 이상 선택해주세요.")

    st.divider()
    st.subheader("총인구수 비교")
    total_pop = df[df["행정구역"] != "전국"][["행정구역", f"{prefix}_계_총인구수"]].sort_values(
        f"{prefix}_계_총인구수", ascending=False)
    fig_bar = px.bar(
        total_pop,
        x="행정구역", y=f"{prefix}_계_총인구수",
        color=f"{prefix}_계_총인구수",
        color_continuous_scale="Blues",
        labels={f"{prefix}_계_총인구수": "총인구수(명)", "행정구역": "지역"},
    )
    fig_bar.update_layout(height=450, coloraxis_showscale=False, template="plotly_white")
    st.plotly_chart(fig_bar, use_container_width=True)


# ----------------------------------------------------------------------------
# TAB 2. 인구 피라미드
# ----------------------------------------------------------------------------
with tab2:
    st.subheader("남녀 인구 피라미드")
    pyramid_region = st.selectbox("지역 선택", options=regions_all, index=regions_all.index("전국") if "전국" in regions_all else 0)

    bin_size = st.slider("연령 구간 크기(세)", min_value=1, max_value=10, value=5, step=1)

    male_counts = get_counts(pyramid_region, cols_male)
    female_counts = get_counts(pyramid_region, cols_female)

    ages_arr = np.array(ages)
    max_age = ages_arr.max()
    bins = list(range(0, max_age + bin_size, bin_size))

    bin_labels, male_binned, female_binned = [], [], []
    for i in range(len(bins) - 1):
        lo, hi = bins[i], bins[i + 1]
        mask = (ages_arr >= lo) & (ages_arr < hi)
        if not mask.any():
            continue
        label = f"{lo}-{hi-1}세" if hi - 1 < max_age else f"{lo}세+"
        bin_labels.append(label)
        male_binned.append(male_counts[mask].sum())
        female_binned.append(female_counts[mask].sum())

    fig_pyr = go.Figure()
    fig_pyr.add_trace(go.Bar(
        y=bin_labels, x=[-v for v in male_binned], orientation="h",
        name="남성", marker_color="#4C78A8",
        hovertemplate="%{y} 남성: %{customdata:,}명<extra></extra>",
        customdata=male_binned,
    ))
    fig_pyr.add_trace(go.Bar(
        y=bin_labels, x=female_binned, orientation="h",
        name="여성", marker_color="#F58518",
        hovertemplate="%{y} 여성: %{x:,}명<extra></extra>",
    ))
    fig_pyr.update_layout(
        barmode="relative",
        height=650,
        title=f"{pyramid_region} 인구 피라미드",
        xaxis_title="인구 수 (명)",
        yaxis_title="연령대",
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig_pyr.update_xaxes(tickvals=None)
    st.plotly_chart(fig_pyr, use_container_width=True)
    st.caption("💡 막대에 마우스를 올리면 실제 인구 수를 확인할 수 있고, 범례 클릭으로 남/여를 개별 확인할 수 있어요.")


# ----------------------------------------------------------------------------
# TAB 3. 쌍둥이 지역 찾기
# ----------------------------------------------------------------------------
with tab3:
    st.subheader("👯 인구 구조가 가장 비슷한 '쌍둥이 지역' 찾기")
    st.caption("연령별 인구 비율(0세~100세 이상)의 분포 형태를 비교하여, 유클리드 거리 기준으로 "
               "가장 인구 구조가 유사한 지역을 찾아줍니다. (전국 제외, 시/도 단위 비교)")

    col1, col2 = st.columns([1, 1])
    with col1:
        base_region = st.selectbox("궁금한 지역을 선택하세요", options=regions_no_national)
    with col2:
        gender_choice2 = st.radio("비교 기준 성별", ["계", "남", "여"], horizontal=True, key="twin_gender")

    gender_cols_map2 = {"계": cols_total, "남": cols_male, "여": cols_female}
    target_cols2 = gender_cols_map2[gender_choice2]

    # 모든 지역의 연령 비율 벡터 생성
    proportions = {r: get_proportion(r, target_cols2) for r in regions_no_national}
    base_vec = proportions[base_region]

    results = []
    for r, vec in proportions.items():
        if r == base_region:
            continue
        euclidean_dist = float(np.sqrt(np.sum((base_vec - vec) ** 2)))
        corr = float(np.corrcoef(base_vec, vec)[0, 1])
        results.append({"지역": r, "유클리드 거리": euclidean_dist, "상관계수": corr})

    result_df = pd.DataFrame(results).sort_values("유클리드 거리").reset_index(drop=True)
    result_df.index = result_df.index + 1
    twin_region = result_df.iloc[0]["지역"]

    st.markdown(f"### 🏆 **{base_region}** 의 쌍둥이 지역은 **{twin_region}** 입니다!")
    st.caption(f"유클리드 거리: {result_df.iloc[0]['유클리드 거리']:.5f}  |  상관계수: {result_df.iloc[0]['상관계수']:.4f} "
               "(거리가 작을수록, 상관계수가 1에 가까울수록 인구 구조가 비슷함을 의미)")

    c1, c2 = st.columns([1, 1])

    with c1:
        st.markdown("**유사도 순위 (거리가 가까운 순)**")
        display_df = result_df.copy()
        display_df["유클리드 거리"] = display_df["유클리드 거리"].map(lambda x: f"{x:.5f}")
        display_df["상관계수"] = display_df["상관계수"].map(lambda x: f"{x:.4f}")
        st.dataframe(display_df, use_container_width=True, height=520)

    with c2:
        st.markdown("**지역별 거리 (짧을수록 유사)**")
        fig_dist = px.bar(
            result_df.sort_values("유클리드 거리", ascending=True),
            x="유클리드 거리", y="지역", orientation="h",
            color="유클리드 거리", color_continuous_scale="RdYlGn_r",
            hover_data={"상관계수": True},
        )
        fig_dist.update_layout(height=520, coloraxis_showscale=False, template="plotly_white",
                                yaxis=dict(categoryorder="total descending"))
        st.plotly_chart(fig_dist, use_container_width=True)

    st.divider()
    st.markdown(f"**{base_region} vs {twin_region} 연령 구조 비교**")

    fig_twin = go.Figure()
    fig_twin.add_trace(go.Scatter(
        x=age_labels, y=base_vec * 100, mode="lines", name=base_region,
        line=dict(width=3, color="#4C78A8"), fill="tozeroy", fillcolor="rgba(76,120,168,0.15)",
    ))
    fig_twin.add_trace(go.Scatter(
        x=age_labels, y=proportions[twin_region] * 100, mode="lines", name=twin_region,
        line=dict(width=3, color="#F58518", dash="dash"),
    ))
    fig_twin.update_layout(
        height=520,
        xaxis_title="연령",
        yaxis_title="인구 비율 (%)",
        hovermode="x unified",
        template="plotly_white",
        xaxis=dict(rangeslider=dict(visible=True), type="category"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig_twin, use_container_width=True)

    # 직접 다른 두 지역끼리 비교해보고 싶을 때
    with st.expander("🔍 다른 두 지역을 직접 비교해보기"):
        cc1, cc2 = st.columns(2)
        with cc1:
            region_x = st.selectbox("지역 A", options=regions_all, key="cmp_a")
        with cc2:
            region_y = st.selectbox("지역 B", options=regions_all,
                                     index=1 if len(regions_all) > 1 else 0, key="cmp_b")
        vec_x = get_proportion(region_x, target_cols2)
        vec_y = get_proportion(region_y, target_cols2)
        dist_xy = float(np.sqrt(np.sum((vec_x - vec_y) ** 2)))
        corr_xy = float(np.corrcoef(vec_x, vec_y)[0, 1])
        st.write(f"**{region_x}** ↔ **{region_y}**  |  유클리드 거리: `{dist_xy:.5f}`  |  상관계수: `{corr_xy:.4f}`")

        fig_cmp = go.Figure()
        fig_cmp.add_trace(go.Scatter(x=age_labels, y=vec_x * 100, mode="lines", name=region_x,
                                      line=dict(width=3)))
        fig_cmp.add_trace(go.Scatter(x=age_labels, y=vec_y * 100, mode="lines", name=region_y,
                                      line=dict(width=3, dash="dash")))
        fig_cmp.update_layout(height=420, xaxis_title="연령", yaxis_title="인구 비율(%)",
                               template="plotly_white", hovermode="x unified",
                               xaxis=dict(rangeslider=dict(visible=True), type="category"))
        st.plotly_chart(fig_cmp, use_container_width=True)

st.divider()
st.caption("데이터 출처: 행정안전부 주민등록 연령별 인구현황 (통계청 통계자료). "
           "본 앱은 시/도 단위 데이터를 기준으로 분석합니다.")
