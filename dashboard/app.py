"""관심 단지 실거래 대시보드.

    streamlit run dashboard/app.py

- 중앙값은 해제·직거래 제외 (직거래 포함 토글 제공), 표본 수(n) 항상 표시
- 색: 단지 = 카테고리 슬롯 1~4 (complexes.yaml 순서 고정), 단지 내 패널 = 거래유형 색
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import importlib  # noqa: E402

import realestate.api.parse  # noqa: E402
from realestate import config, db, metrics  # noqa: E402

# src/는 Streamlit 자동 재로드 범위(dashboard/) 밖이라, 서버가 켜진 채 git pull 하면 옛 모듈이 메모리에 남는다.
# 매 실행마다 다시 읽어 app.py와 항상 같은 버전을 쓰게 한다 (의존 순서대로).
from realestate import listings  # noqa: E402

for _mod in (realestate.api.parse, config, db, metrics, listings):
    importlib.reload(_mod)
LISTING_RAW_DIR = config.DATA_DIR / "listings" / "raw"

st.set_page_config(page_title="관심 단지 실거래", layout="wide")
PAGE_MAX_W = 980  # 본문 최대 폭(px): 넓은 화면에서도 차트가 과하게 늘어나지 않게
st.markdown(f"""<style>
.block-container, [data-testid="stMainBlockContainer"] {{ max-width: {PAGE_MAX_W}px; padding-left: 1rem; padding-right: 1rem; }}
</style>""", unsafe_allow_html=True)

# ───── 색 (dataviz 기본 팔레트, 라이트/다크 각각 검증) ─────
DARK = getattr(getattr(st.context, "theme", None), "type", None) == "dark"
C = {
    "complex": ["#3987e5", "#d95926", "#199e70", "#c98500"] if DARK else ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"],
    "broker": "#9085e9" if DARK else "#4a3aa7",     # 중개거래 (violet)
    "direct": "#d55181" if DARK else "#e87ba4",     # 직거래 (magenta)
    "jeonse": "#008300",                            # 전세·신규 전세 (green)
    "renew": "#9085e9" if DARK else "#4a3aa7",      # 갱신 전세 (violet)
    "wolse": "#c98500" if DARK else "#eda100",      # 월세 (yellow)
    "ink": "#ffffff" if DARK else "#0b0b0b",        # 매매 중앙값 선
    "ink2": "#c3c2b7" if DARK else "#52514e",
    "muted": "#898781",                             # 해제, 보조선
    "grid": "#2c2c2a" if DARK else "#e1e0d9",
}
FONT = dict(family='system-ui, -apple-system, "Segoe UI", sans-serif', size=13)


def eok(v):  # 만원 → '14.5억'
    return "" if pd.isna(v) else f"{v / 10000:.2f}억".replace(".00억", "억")


X_RANGE: list = []  # 모든 차트 공통 x 범위 (필터 적용 후 설정) → 같은 시점이 같은 세로선에


def style(fig: go.Figure, height: int, hovermode: str = "closest") -> go.Figure:
    # 좌우 여백 고정(automargin 끔) → 차트마다 플롯 영역 폭이 같아 세로선이 페이지 전체에서 맞음
    fig.update_layout(height=height, font=FONT, margin=dict(l=64, r=16, t=64, b=36, autoexpand=False),
                      legend=dict(orientation="h", yref="container", yanchor="top", y=1, x=0),
                      hoverlabel=dict(font=FONT), plot_bgcolor="rgba(0,0,0,0)", hovermode=hovermode)
    fig.update_xaxes(range=X_RANGE, showgrid=True, gridcolor=C["grid"], gridwidth=1,
                     dtick="M6", tick0="2024-01-01", tickformat="%Y-%m",
                     linecolor=C["grid"], ticks="outside", tickcolor=C["grid"],
                     showspikes=True, spikemode="across", spikesnap="cursor", spikethickness=1,
                     spikedash="solid", spikecolor=C["muted"])
    fig.update_yaxes(gridcolor=C["grid"], gridwidth=1, zeroline=False, tickformat=",", automargin=False,
                     title_standoff=8)
    return fig


def stacked(titles: list[str], row_px: int, gap_px: int = 48) -> tuple[go.Figure, int]:
    """단지별 패널을 위아래로 쌓고 x축 공유. (fig, 전체 높이)"""
    n = len(titles)
    height = row_px * n + gap_px * (n - 1) + 100
    fig = make_subplots(rows=n, cols=1, shared_xaxes=True, subplot_titles=titles,
                        vertical_spacing=gap_px / (height - 100))
    for a in fig.layout.annotations:  # 패널 제목 왼쪽 정렬
        a.update(x=0, xanchor="left", font=dict(size=13, color=C["ink2"]))
    return fig, height


def cap_line(fig, cap, row=None, col=None, label_left=False):
    kw = dict(row=row, col=col) if row else {}
    fig.add_hline(y=cap / 10000, line=dict(color=C["muted"], width=1),
                  annotation=dict(text=f"상한 {eok(cap)}", font=dict(color=C["ink2"], size=10),
                                  x=0 if label_left else 1, xanchor="left" if label_left else "right",
                                  yanchor="bottom"), **kw)


# ───── 데이터 ─────
@st.cache_data(show_spinner=False)
def load(db_file: str, mtime: float, raw_sig: tuple):
    settings = config.load_settings()
    conn = db.connect(db_file)
    db.init_db(conn)
    db.sync_config(conn, settings, config.load_complexes())
    listings.ingest_dir(conn, LISTING_RAW_DIR)  # 새 매물 덤프 파일이 있으면 적재 (멱등)
    trades = metrics.load_trades(conn, include_canceled=True)
    rents = metrics.load_rents(conn, rent_type=None)
    cx = pd.read_sql_query("SELECT complex_id, name, target_bands FROM complex", conn)
    snap = listings.snapshot(conn, settings)
    n_dumps = conn.execute("SELECT COUNT(*), MAX(snap_date) FROM listing_raw").fetchone()
    paths = listings.available_paths(conn) if n_dumps[0] else None
    conn.close()
    return settings, trades, rents, cx, snap, tuple(n_dumps), paths


db_file = str(config.db_path())
if not Path(db_file).exists():
    st.error(f"DB가 없습니다: {db_file} — 먼저 `python -m realestate.ingest` 실행")
    st.stop()
settings, trades_all, rents_all, cx, listing_snap, (n_dumps, last_dump), listing_paths = load(
    db_file, Path(db_file).stat().st_mtime, listings.raw_dir_signature(LISTING_RAW_DIR))
order = list(cx["complex_id"])                      # complexes.yaml 순서 = 색 슬롯
names = dict(zip(cx["complex_id"], cx["name"]))
color_of = {cid: C["complex"][i % 4] for i, cid in enumerate(order)}
bands_of = {r.complex_id: (r.target_bands or "").split(",") for r in cx.itertuples()}
cap = settings.get("buy_cap_manwon", 140000)

st.title("관심 단지 실거래 동향")

# ───── 필터 (한 줄) ─────
all_months = metrics.month_range(trades_all["deal_ym"].min(), trades_all["deal_ym"].max())
f1, f2, f3 = st.columns([1.3, 3, 2.7])
BANDS = ["59", "74", "84"]
q_band = st.query_params.get("band", "84")
band = f1.radio("평형", BANDS, index=BANDS.index(q_band) if q_band in BANDS else 2, horizontal=True)
avail = [c for c in order if band in bands_of[c]]
sel = f2.multiselect("단지", avail, default=avail, format_func=names.get)
start, end = f3.select_slider("기간", options=all_months, value=(all_months[0], all_months[-1]))
t1, t2, t3 = st.columns(3)
incl_direct = t1.toggle("직거래를 매매 중앙값에 포함", value=False)
incl_renew = t2.toggle("갱신 계약을 전세 중앙값에 포함", value=False,
                       help="갱신은 인상률 5% 상한이 있어 시세보다 낮음. 기본은 신규(+유형 미상)만")
show_cancel = t3.toggle("해제 건 표시(산점도)", value=True)

if not sel:
    st.info("단지를 하나 이상 선택하세요.")
    st.stop()
months = metrics.month_range(start, end)
in_scope = lambda df: df[df["complex_id"].isin(sel) & (df["size_band"] == band)  # noqa: E731
                         & df["deal_ym"].between(start, end)]
T = in_scope(trades_all)
R = in_scope(rents_all)
base = T[(T["is_canceled"] == 0) & (incl_direct | (T["dealing_gbn"] != "직거래"))]
renew_ok = lambda df: incl_renew | (df["contract_type"] != "갱신")  # noqa: E731 (미상은 포함)
J = R[(R["rent_type"] == "전세") & renew_ok(R)]

# 3개월 이동중앙값은 기간 시작 전 2개월 거래도 사용해야 첫 달부터 정확
lead = [p.strftime("%Y-%m") for p in pd.period_range(end=pd.Period(start), periods=3, freq="M")]
base_ext = trades_all[trades_all["complex_id"].isin(sel) & (trades_all["size_band"] == band)
                      & trades_all["deal_ym"].between(lead[0], end) & (trades_all["is_canceled"] == 0)
                      & (incl_direct | (trades_all["dealing_gbn"] != "직거래"))]
J_ext = rents_all[rents_all["complex_id"].isin(sel) & (rents_all["size_band"] == band)
                  & rents_all["deal_ym"].between(lead[0], end) & (rents_all["rent_type"] == "전세")
                  & renew_ok(rents_all)]
ext_months = lead[:-1] + months
roll_t = metrics.window_median(base_ext, "deal_amount", 3, months=ext_months)
roll_t = roll_t[roll_t["deal_ym"].isin(months)]
roll_j = metrics.window_median(J_ext, "deposit", 3, months=ext_months)
roll_j = roll_j[roll_j["deal_ym"].isin(months)]
x_of = lambda ym: pd.Period(ym).to_timestamp() + pd.Timedelta(days=14)  # noqa: E731 (월 중순에 점)
X_RANGE[:] = [pd.Period(months[0]).to_timestamp() - pd.Timedelta(days=10),
              pd.Period(months[-1]).to_timestamp() + pd.Timedelta(days=75)]  # 오른쪽 여유: 끝점 라벨

st.caption(f"{band}형 · {start} ~ {end} · 매매 중앙값: 해제 제외, 직거래 {'포함' if incl_direct else '제외'} · "
           f"전세 중앙값: 갱신 {'포함' if incl_renew else '제외'} · "
           f"3개월 이동중앙값 = 해당 월 포함 직전 3개월 거래를 모아 계산 · 거래 없는 달은 앞뒤 값을 직선으로 연결 · 금액 단위 억원")

facet_titles = lambda: [names[c] for c in sel]  # noqa: E731

# ① 매매 산점도 + 3개월 이동중앙값
st.subheader("① 매매 실거래 + 3개월 이동중앙값")
fig, h = stacked(facet_titles(), 230)
for i, cid in enumerate(sel):
    r, c = i + 1, 1
    d = T[T["complex_id"] == cid]
    groups = [("중개거래", d[(d["is_canceled"] == 0) & (d["dealing_gbn"] != "직거래")], C["broker"], "circle"),
              ("직거래", d[(d["is_canceled"] == 0) & (d["dealing_gbn"] == "직거래")], C["direct"], "diamond")]
    if show_cancel:
        groups.append(("해제", d[d["is_canceled"] == 1], C["muted"], "x-thin-open"))
    for label, g, col, sym in groups:
        fig.add_trace(go.Scatter(
            x=g["deal_date"], y=g["deal_amount"] / 10000, mode="markers", name=label, legendgroup=label,
            showlegend=i == 0, marker=dict(color=col, size=8, symbol=sym,
                                           line=dict(width=1.5 if sym.startswith("x") else 1,
                                                     color=col if sym.startswith("x") else "rgba(255,255,255,0.9)")),
            customdata=g[["apt_dong", "floor", "exclu_use_ar", "dealing_gbn", "cancel_date"]].fillna(""),
            hovertemplate="<b>%{y:.2f}억</b><br>%{x|%Y-%m-%d} · %{customdata[0]}동 %{customdata[1]}층<br>"
                          "전용 %{customdata[2]}㎡ · %{customdata[3]} %{customdata[4]}<extra>" + label + "</extra>",
        ), row=r, col=c)
    m = roll_t[roll_t["complex_id"] == cid]
    fig.add_trace(go.Scatter(
        x=m["deal_ym"].map(x_of), y=m["median"] / 10000, mode="lines", name="3개월 이동중앙값",
        legendgroup="med", showlegend=i == 0, line=dict(color=C["ink"], width=2), connectgaps=True,
        customdata=m[["n"]], hovertemplate="<b>%{y:.2f}억</b> (n=%{customdata[0]})<br>%{x|%Y-%m}<extra>3개월 중앙값</extra>",
    ), row=r, col=c)
    cap_line(fig, cap, r, c)
    n_ok = len(d[d["is_canceled"] == 0])
    fig.layout.annotations[i].text = f"{names[cid]} <span style='font-size:11px'>n={n_ok}</span>"
fig.update_yaxes(title_text="억원")
st.plotly_chart(style(fig, h), use_container_width=True)
with st.expander("표로 보기 — 월별 3개월 이동중앙값"):
    tbl = roll_t.pivot_table(index="deal_ym", columns="complex_name", values=["median", "n"], aggfunc="first")
    st.dataframe(tbl, use_container_width=True)

# ② 월별 거래량 (해제 별도 색)
st.subheader("② 월별 거래량")
fig, h = stacked(facet_titles(), 130)
vol_rows = []
for i, cid in enumerate(sel):
    r, c = i + 1, 1
    d = T[T["complex_id"] == cid]
    kinds = {"중개거래": (d["is_canceled"] == 0) & (d["dealing_gbn"] != "직거래"),
             "직거래": (d["is_canceled"] == 0) & (d["dealing_gbn"] == "직거래"),
             "해제": d["is_canceled"] == 1}
    for label, col in (("중개거래", C["broker"]), ("직거래", C["direct"]), ("해제", C["muted"])):
        cnt = d[kinds[label]].groupby("deal_ym").size().reindex(months, fill_value=0)
        vol_rows += [(names[cid], ym, label, int(v)) for ym, v in cnt.items()]
        fig.add_trace(go.Bar(x=[x_of(m) for m in months], y=cnt.values, name=label, legendgroup=label,
                             showlegend=i == 0, marker=dict(color=col, line=dict(width=0)),
                             hovertemplate="<b>%{y}건</b> %{x|%Y-%m}<extra>" + label + "</extra>"),
                      row=r, col=c)
fig.update_layout(barmode="stack", bargap=0.25)
style(fig, h, hovermode="x unified")
vol = pd.DataFrame(vol_rows, columns=["단지", "월", "유형", "건수"])
vmax = int(vol.groupby(["단지", "월"])["건수"].sum().max()) if not vol.empty else 1
fig.update_yaxes(title_text="건", tickformat="d", range=[0, max(vmax, 1) * 1.1])  # 모든 패널 같은 y축 (건수 비교)
st.plotly_chart(fig, use_container_width=True)
with st.expander("표로 보기 — 월별 거래량"):
    st.dataframe(vol.pivot_table(index="월", columns=["단지", "유형"], values="건수", aggfunc="sum"),
                 use_container_width=True)

# ③ 전세·매매 추이 (같은 축)
st.subheader("③ 매매 vs 전세 (3개월 이동중앙값, 같은 축)")
if J.empty and J_ext.empty:
    st.info("전월세 데이터가 아직 없습니다 (전월세 API 활용신청 승인 후 `python -m realestate.ingest --api rent`).")
else:
    fig, h = stacked(facet_titles(), 200)
    for i, cid in enumerate(sel):
        r, c = i + 1, 1
        for label, df, col in (("매매", roll_t, C["ink"]), ("전세", roll_j, C["jeonse"])):
            m = df[df["complex_id"] == cid]
            fig.add_trace(go.Scatter(
                x=m["deal_ym"].map(x_of), y=m["median"] / 10000, mode="lines", name=label, legendgroup=label,
                showlegend=i == 0, line=dict(color=col, width=2), connectgaps=True, customdata=m[["n"]],
                hovertemplate="<b>%{y:.2f}억</b> (n=%{customdata[0]})<br>%{x|%Y-%m}<extra>" + label + "</extra>",
            ), row=r, col=c)
        cap_line(fig, cap, r, c)
    fig.update_yaxes(title_text="억원")
    st.plotly_chart(style(fig, h, hovermode="x unified"), use_container_width=True)

# ④ 전세가율
st.subheader("④ 전세가율 (전세 보증금 중앙값 ÷ 매매 중앙값, 같은 단지·평형)")
if J.empty and J_ext.empty:
    st.info("전월세 데이터가 들어오면 표시됩니다.")
else:
    win = st.radio("집계 창", [3, 1], horizontal=True, format_func=lambda w: "같은 월" if w == 1 else "3개월",
                   help="기본 3개월: 직전 3개월 거래를 모아 중앙값 (월별 표본이 적어 같은 월은 변동이 큼)")
    jr = metrics.jeonse_ratio(base_ext, J_ext, window=win, months=ext_months)
    jr = jr[jr["deal_ym"].isin(months)]
    fig = go.Figure()
    for cid in sel:
        m = jr[jr["complex_id"] == cid]
        fig.add_trace(go.Scatter(
            x=m["deal_ym"].map(x_of), y=m["ratio"] * 100, mode="lines+markers", name=names[cid],
            line=dict(color=color_of[cid], width=2), connectgaps=True, marker=dict(size=8, line=dict(width=2, color="rgba(255,255,255,0.9)")),
            customdata=m[["trade_median", "trade_n", "jeonse_median", "jeonse_n"]].fillna(0),
            hovertemplate="<b>%{y:.1f}%</b> %{x|%Y-%m}<br>매매 %{customdata[0]:,.0f}만 (n=%{customdata[1]})"
                          "<br>전세 %{customdata[2]:,.0f}만 (n=%{customdata[3]})<extra>" + names[cid] + "</extra>"))
    fig.update_yaxes(title_text="%", tickformat=".0f")
    st.plotly_chart(style(fig, 380, hovermode="x unified"), use_container_width=True)
    with st.expander("표로 보기 — 전세가율"):
        st.dataframe(jr, use_container_width=True)

# ⑤ 전세 공급 대리지표 (전월세 거래 구성)
st.subheader("⑤ 전세 공급 지표 (전월세 거래 구성)")
R_ext = rents_all[rents_all["complex_id"].isin(sel) & (rents_all["size_band"] == band)
                  & rents_all["deal_ym"].between(lead[0], end)]
if R_ext.empty:
    st.info("전월세 데이터가 들어오면 표시됩니다.")
else:
    st.caption("갱신 비율↑ = 기존 세입자 잔류로 새로 나오는 전세가 줄어듦(공급 감소 신호). "
               "월세 비중↑ = 전세가 월세로 전환되는 흐름. 비율은 직전 3개월 거래를 모아 계산.")
    rc = metrics.rent_composition(R_ext, ext_months)
    rc = rc[rc["deal_ym"].isin(months)]
    fig, h = stacked(facet_titles(), 130)
    for i, cid in enumerate(sel):
        m = rc[rc["complex_id"] == cid]
        for col_name, label, color in (("new_jeonse", "신규 전세", C["jeonse"]), ("renew_jeonse", "갱신 전세", C["renew"]),
                                       ("wolse", "월세", C["wolse"])):
            fig.add_trace(go.Bar(x=m["deal_ym"].map(x_of), y=m[col_name], name=label, legendgroup=label,
                                 showlegend=i == 0, marker=dict(color=color, line=dict(width=0)),
                                 hovertemplate="<b>%{y}건</b> %{x|%Y-%m}<extra>" + label + "</extra>"),
                          row=i + 1, col=1)
    rmax = int((rc["new_jeonse"] + rc["renew_jeonse"] + rc["wolse"]).max() or 1)
    fig.update_layout(barmode="stack", bargap=0.25)
    style(fig, h, hovermode="x unified")
    fig.update_yaxes(title_text="건", tickformat="d", range=[0, rmax * 1.1])
    st.plotly_chart(fig, use_container_width=True)

    RATIO_MIN_N = 5  # 3개월 창 표본이 이보다 적으면 비율 생략 (0%/100% 튐 방지, 선은 앞뒤 연결)
    for col_name, n_col, title in (("renew_ratio", "renew_n", "갱신 비율 (갱신 전세 ÷ 전세 전체, 3개월)"),
                                   ("wolse_share", "total_n", "월세 비중 (월세 ÷ 전월세 전체, 3개월)")):
        st.markdown(f"**{title}** <span style='font-size:12px;opacity:.7'>· 3개월 표본 {RATIO_MIN_N}건 미만은 생략</span>",
                    unsafe_allow_html=True)
        fig = go.Figure()
        for cid in sel:
            m = rc[rc["complex_id"] == cid]
            m = m.assign(**{col_name: m[col_name].where(m[n_col] >= RATIO_MIN_N)})
            fig.add_trace(go.Scatter(
                x=m["deal_ym"].map(x_of), y=m[col_name] * 100, mode="lines", name=names[cid], connectgaps=True,
                line=dict(color=color_of[cid], width=2), customdata=m[[n_col]],
                hovertemplate="<b>%{y:.0f}%</b> (n=%{customdata[0]})<br>%{x|%Y-%m}<extra>" + names[cid] + "</extra>"))
        style(fig, 300, hovermode="x unified")
        fig.update_yaxes(title_text="%", tickformat=".0f", range=[0, 100])
        st.plotly_chart(fig, use_container_width=True)
    with st.expander("표로 보기 — 전월세 거래 구성"):
        st.dataframe(rc.drop(columns=["complex_id", "size_band"]), use_container_width=True, hide_index=True)

# ⑥ 같은 평형 단지 간 비교
st.subheader(f"⑥ {band}형 단지 간 비교 (3개월 이동중앙값)")
fig = go.Figure()
for cid in sel:
    m = roll_t[roll_t["complex_id"] == cid]
    fig.add_trace(go.Scatter(
        x=m["deal_ym"].map(x_of), y=m["median"] / 10000, mode="lines", name=names[cid],
        line=dict(color=color_of[cid], width=2), connectgaps=True, customdata=m[["n"]],
        hovertemplate="<b>%{y:.2f}억</b> (n=%{customdata[0]})<br>%{x|%Y-%m}<extra>" + names[cid] + "</extra>"))
# 끝점 직접 라벨: 값이 가까워 겹치면 생략 (범례·툴팁·표가 대신)
ends = []
for cid in sel:
    last = roll_t[roll_t["complex_id"] == cid].dropna(subset=["median"]).tail(1)
    if not last.empty:
        ends.append((last["median"].iloc[0], cid, last))
placed: list[float] = []
for val, cid, last in sorted(ends, key=lambda e: e[0]):
    fig.add_trace(go.Scatter(x=last["deal_ym"].map(x_of), y=[val / 10000], mode="markers",
                             marker=dict(color=color_of[cid], size=9, line=dict(width=2, color="rgba(255,255,255,0.9)")),
                             showlegend=False, hoverinfo="skip"))
    if all(abs(val - p) >= 4000 for p in placed):  # 0.4억 이상 떨어진 경우만
        placed.append(val)
        fig.add_annotation(x=last["deal_ym"].map(x_of).iloc[0], y=val / 10000, text=eok(val), showarrow=False,
                           xanchor="left", xshift=8, font=dict(color=C["ink2"], size=12))
cap_line(fig, cap, label_left=True)  # 오른쪽은 끝점 라벨 자리
fig.update_yaxes(title_text="억원")
st.plotly_chart(style(fig, 420, hovermode="x unified"), use_container_width=True)


def trailing3(cid: str, ym: str) -> tuple[float, int]:
    """ym 기준 직전 3개월 풀링 중앙값 (기간 필터와 무관하게 전체 데이터에서)."""
    d = trades_all[(trades_all["complex_id"] == cid) & (trades_all["size_band"] == band)
                   & (trades_all["is_canceled"] == 0) & (incl_direct | (trades_all["dealing_gbn"] != "직거래"))]
    w = metrics.window_median(d, "deal_amount", 3,
                              months=metrics.month_range((pd.Period(ym) - 2).strftime("%Y-%m"), ym)).tail(1)
    return (w["median"].iloc[0], int(w["n"].iloc[0])) if not w.empty else (float("nan"), 0)


def summary_row(cid: str) -> dict:
    """가장 최근에 거래가 있는 3개월 창 기준. 1년 전 같은 창과 비교."""
    m = roll_t[(roll_t["complex_id"] == cid) & (roll_t["n"] > 0)]
    d = T[(T["complex_id"] == cid) & (T["is_canceled"] == 0)].sort_values("deal_date")
    row = {"단지": names[cid]}
    if m.empty:
        return row | {"기준월": "", "3개월 중앙값": "", "n": "0 ⚠ 표본 적음"}
    ref = m.iloc[-1]
    ym, med, n = ref["deal_ym"], ref["median"], int(ref["n"])
    ago_med, ago_n = trailing3(cid, (pd.Period(ym) - 12).strftime("%Y-%m"))
    return row | {
        "기준월": ym, "3개월 중앙값": eok(med), "n": f"{n} ⚠ 표본 적음" if n < 3 else str(n),
        "1년 전 중앙값 (n)": f"{eok(ago_med)} ({ago_n})" if ago_n else "",
        "변화": "" if not ago_n else f"{(med / ago_med - 1) * 100:+.1f}%",
        "상한 대비": f"{(med - cap) / 10000:+.2f}억",
        "최근 거래": "" if d.empty else f"{d['deal_date'].iloc[-1]:%Y-%m-%d} {eok(d['deal_amount'].iloc[-1])}",
    }


st.dataframe(pd.DataFrame([summary_row(c) for c in sel]), hide_index=True, use_container_width=True)
st.caption("기준월 = 거래가 있는 가장 최근 3개월 창의 마지막 월. n = 중앙값 계산에 쓰인 거래 수. "
           "최근 1~2개월은 신고 기한(30일)이 남아 건수가 늘어날 수 있음.")

# ⑦ 네이버 매물 추이 (북마클릿 덤프)
st.subheader("⑦ 네이버 매물 추이")
if not n_dumps:
    st.info("아직 매물 덤프가 없습니다. 크롬에서 fin.land.naver.com 을 연 뒤 북마클릿(📥 네이버 매물 덤프)을 누르고 "
            "`python3 scripts/save_listings.py` 를 실행하면 여기에 쌓입니다. (설치: tools/bookmarklet.html)")
else:
    LS = listing_snap[listing_snap["complex_id"].isin(sel)] if not listing_snap.empty else listing_snap
    # 단지 전체(pyeongTypeNumber 0 또는 없음) 기준. 평형별은 경로 확정 후 추가
    LS_all = LS[LS["pyeong_type"].isna() | (LS["pyeong_type"] == 0)] if not LS.empty else LS
    st.caption(f"덤프 {n_dumps}회 · 최근 {last_dump} · 값은 네이버페이 부동산 화면 기준(단지 전체). "
               "매물 수 증감이 실거래가에 앞서는지 보는 용도.")
    if LS_all.empty:
        st.warning("덤프는 있지만 settings.yaml `listing_metrics` 경로 규칙에 맞는 값이 없습니다. "
                   "아래 '수집된 경로 보기'에서 경로를 확인해 규칙을 고치면 표시됩니다.")
    else:
        def _series(metric):
            m = LS_all[LS_all["metric"] == metric]
            return m.pivot_table(index="snap_date", columns="complex_id", values="value", aggfunc="last")

        cnt_sale, cnt_lease, cnt_wolse = _series("sale_count"), _series("lease_count"), _series("wolse_count")
        fig, h = stacked(facet_titles(), 150)
        for i, cid in enumerate(sel):
            for label, tbl, col in (("매매 매물", cnt_sale, C["ink"]), ("전세 매물", cnt_lease, C["jeonse"]),
                                    ("월세 매물", cnt_wolse, C["wolse"])):
                if cid not in tbl.columns:
                    continue
                s_ = tbl[cid].dropna()
                fig.add_trace(go.Scatter(x=pd.to_datetime(s_.index), y=s_.values, mode="lines+markers", name=label,
                                         legendgroup=label, showlegend=i == 0, connectgaps=True,
                                         line=dict(color=col, width=2), marker=dict(size=7),
                                         hovertemplate="<b>%{y:.0f}건</b> %{x|%Y-%m-%d}<extra>" + label + "</extra>"),
                              row=i + 1, col=1)
        style(fig, h, hovermode="x unified")
        lo = pd.to_datetime(LS_all["snap_date"].min()) - pd.Timedelta(days=3)
        hi = pd.to_datetime(LS_all["snap_date"].max()) + pd.Timedelta(days=3)
        fig.update_xaxes(range=[lo, hi], dtick=None, tickformat="%m-%d")
        fig.update_yaxes(title_text="건", tickformat="d", rangemode="tozero")
        st.plotly_chart(fig, use_container_width=True)

        ask = _series("sale_min_ask")
        if not ask.empty:
            fig = go.Figure()
            for cid in sel:
                if cid in ask.columns:
                    s_ = ask[cid].dropna() / 1e8  # 원 → 억
                    fig.add_trace(go.Scatter(x=pd.to_datetime(s_.index), y=s_.values, mode="lines+markers",
                                             name=names[cid], line=dict(color=color_of[cid], width=2),
                                             marker=dict(size=7), connectgaps=True,
                                             hovertemplate="<b>%{y:.2f}억</b> %{x|%Y-%m-%d}<extra>" + names[cid] + "</extra>"))
            cap_line(fig, cap, label_left=True)
            style(fig, 320, hovermode="x unified")
            fig.update_xaxes(range=[lo, hi], dtick=None, tickformat="%m-%d")
            fig.update_yaxes(title_text="매매 최저 호가 (억원)")
            st.markdown("**매매 최저 호가**")
            st.plotly_chart(fig, use_container_width=True)
    with st.expander("표로 보기 — 매물 스냅샷"):
        st.dataframe(LS_all.pivot_table(index=["snap_date", "complex_id"], columns="metric", values="value",
                                        aggfunc="last") if not LS_all.empty else LS_all, use_container_width=True)
    with st.expander("수집된 경로 보기 (경로 규칙 확정용)"):
        st.dataframe(listing_paths, use_container_width=True, hide_index=True)
