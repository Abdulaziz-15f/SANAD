from typing import Optional
import folium
import streamlit.components.v1 as components


import streamlit as st


def header(project_name: str):
    st.markdown('<div class="sg-header">', unsafe_allow_html=True)
    st.markdown(f'<div class="sg-title">{project_name}</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sg-subtitle">Smart Automated Network for Auditing and Design Compliance</div>',
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown('<div class="sg-divider"></div>', unsafe_allow_html=True)


def render_map(
    lat: float, lon: float, label: str | None, height: int = 320, zoom: int = 6
):
    import folium
    import streamlit.components.v1 as components

    m = folium.Map(
        location=[lat, lon],
        zoom_start=zoom,
        tiles="CartoDB Positron",
        control_scale=True,
    )

    tip = label or "Selected site"

   
    d = 0.08  # size of square (visual only)

    folium.Rectangle(
        bounds=[
            [lat - d, lon - d],
            [lat + d, lon + d],
        ],
        color="#2E7D6F",  # dark SANAD green
        weight=3,
        fill=True,
        fill_color="#5FAF9E",
        fill_opacity=0.18,
        tooltip=tip,
    ).add_to(m)

    folium.CircleMarker(
        location=[lat, lon],
        radius=6,
        color="#FFFFFF",
        weight=2,
        fill=True,
        fill_color="#2E7D6F",
        fill_opacity=1,
        tooltip=tip,
    ).add_to(m)

    html = m.get_root().render()
    components.html(html, height=height, scrolling=False)


def weather_summary(
    place: Optional[str],
    current_temp: Optional[float],
    tmin: Optional[float],
    tmin_method: Optional[str],
    tmax: Optional[float] = None,
    max_wind_speed: Optional[float] = None,
    current_wind_speed: Optional[float] = None,
) -> None:
    """Render weather summary card with all climate data."""
    import streamlit as st

    st.markdown(
        """
        <div class="sg-card">
            <div class="sg-card-title">Current temperature</div>
            <div class="sg-card-value">{curr_temp} <span class="sg-card-unit">°C</span></div>
            <div style="display: flex; justify-content: space-between; margin-top: 1rem;">
                <div>
                    <div class="sg-card-subtitle">Lowest (10Y)</div>
                    <div class="sg-card-value-sm">{tmin} <span class="sg-card-unit">°C</span></div>
                </div>
                <div>
                    <div class="sg-card-subtitle">Highest (10Y)</div>
                    <div class="sg-card-value-sm">{tmax} <span class="sg-card-unit">°C</span></div>
                </div>
            </div>
            <div style="display: flex; justify-content: space-between; margin-top: 1rem;">
                <div>
                    <div class="sg-card-subtitle">Current wind</div>
                    <div class="sg-card-value-sm">{curr_wind} <span class="sg-card-unit">km/h</span></div>
                </div>
                <div>
                    <div class="sg-card-subtitle">Max wind gust (10Y)</div>
                    <div class="sg-card-value-sm">{max_wind} <span class="sg-card-unit">km/h</span></div>
                </div>
            </div>
            <div class="sg-card-footer">
                <div><b>Site:</b> {place}</div>
                <div class="sg-badge">{method}</div>
            </div>
        </div>
        """.format(
            curr_temp=f"{current_temp:.1f}" if current_temp is not None else "—",
            tmin=f"{tmin:.1f}" if tmin is not None else "—",
            tmax=f"{tmax:.1f}" if tmax is not None else "—",
            curr_wind=f"{current_wind_speed:.1f}" if current_wind_speed is not None else "—",
            max_wind=f"{max_wind_speed:.1f}" if max_wind_speed is not None else "—",
            place=place or "Not selected",
            method=tmin_method or "",
        ),
        unsafe_allow_html=True,
    )


import streamlit as st


def result_card(
    title: str,
    level: str,
    subtitle: str,
    bullets: list[str],
    right_metric: tuple[str, str] | None = None,
):
    """
    level: PASS / WARN / FAIL / INFO
    """
    level = (level or "INFO").upper()
    cls = {
        "PASS": "sg-res pass",
        "WARN": "sg-res warn",
        "FAIL": "sg-res fail",
        "INFO": "sg-res info",
    }.get(level, "sg-res info")

    badge = {
        "PASS": "MATCH",
        "WARN": "WARNING",
        "FAIL": "CRITICAL",
        "INFO": "INFO",
    }.get(level, "INFO")

    metric_html = ""
    if right_metric:
        k, v = right_metric
        metric_html = f"""
        <div class="sg-res-metric">
          <div class="k">{k}</div>
          <div class="v">{v}</div>
        </div>
        """

    items = "".join([f"<li>{b}</li>" for b in (bullets or [])])

    st.markdown(
        f"""
        <div class="{cls}">
          <div class="sg-res-top">
            <div>
              <div class="sg-res-title">{title}</div>
              <div class="sg-res-sub">{subtitle}</div>
            </div>
            <div class="sg-res-right">
              <div class="sg-res-badge">{badge}</div>
              {metric_html}
            </div>
          </div>

          <div class="sg-res-body">
            <ul>{items}</ul>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def kpi_row(items: list[tuple[str, str]]):
    """
    items: [(label, value), ...]
    """
    cells = "".join(
        [
            f'<div class="sg-kpi"><div class="l">{k}</div><div class="v">{v}</div></div>'
            for k, v in items
        ]
    )
    st.markdown(f'<div class="sg-kpi-grid">{cells}</div>', unsafe_allow_html=True)
