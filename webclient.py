
from __future__ import annotations

import os
from typing import Any

import pandas as pd
import plotly.express as px
import pydeck as pdk
import requests
import streamlit as st

st.set_page_config(
    page_title="Flock Energy | Grid Intelligence",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --------------------------------------------------
# Configuration
# --------------------------------------------------

API_URL = os.getenv("FLOCK_API_URL", "http://127.0.0.1:8000").rstrip("/")

# Set these to the authentication routes already implemented
# in your FastAPI backend.
LOGIN_PATH = os.getenv("FLOCK_LOGIN_PATH", "/api/v1/auth/login")
ME_PATH = os.getenv("FLOCK_ME_PATH", "/api/v1/auth/me")
LOGOUT_PATH = os.getenv("FLOCK_LOGOUT_PATH", "/api/v1/auth/logout")

CSS_PATH = os.path.join(os.path.dirname(__file__), "style.css")

try:
    with open(CSS_PATH, encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
except OSError:
    st.warning("style.css not found. Place it beside streamlit_app.py.")


# --------------------------------------------------
# API and authentication
# --------------------------------------------------

def get_session():
    return st.session_state.get("api_session")


def response_error(response):
    try:
        body = response.json()
        if isinstance(body, dict):
            error = body.get("error", {})
            if isinstance(error, dict):
                return error.get("message", "Request failed.")
            return body.get("detail", "Request failed.")
    except ValueError:
        pass

    return f"Request failed ({response.status_code})."


def api_request(method, path, **kwargs):
    session = get_session()

    if session is None:
        st.session_state.authenticated = False
        raise RuntimeError("Your session has expired. Please sign in again.")

    try:
        response = session.request(
            method,
            f"{st.session_state.api_url}{path}",
            timeout=45,
            **kwargs,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not connect to the API: {exc}") from exc

    if response.status_code == 401:
        st.session_state.authenticated = False
        st.session_state.api_session = None
        raise RuntimeError("Your session has expired. Please sign in again.")

    if not response.ok:
        raise RuntimeError(response_error(response))

    if not response.content:
        return None

    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError("The API returned an invalid response.") from exc


def login_view():
    st.markdown("""
    <div class="login-hero">
        <div class="eyebrow">FLOCK ENERGY</div>
        <h1>Grid Intelligence</h1>
        <p>Distribution network monitoring and analytics.</p>
    </div>
    """, unsafe_allow_html=True)

    _, center, _ = st.columns([1, 1.1, 1])

    with center:
        with st.container(border=True):
            st.subheader("Sign in")

            api_url = st.text_input("API base URL", value=API_URL)

            with st.form("login_form"):
                username = st.text_input("Username / Email")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button(
                    "Sign in",
                    type="primary",
                    use_container_width=True,
                )

            if submitted:
                clean_url = api_url.strip().rstrip("/")

                if not clean_url.startswith(("http://", "https://")):
                    st.error("Please enter a valid API URL.")
                    return

                session = requests.Session()

                try:
                    response = session.post(
                        clean_url + LOGIN_PATH,
                        json={
                            "username": username,
                            "password": password,
                        },
                        timeout=20,
                    )

                    if not response.ok:
                        st.error(response_error(response))
                        return

                    # Verify that the backend accepted the session.
                    verification = session.get(
                        clean_url + ME_PATH,
                        timeout=20,
                    )

                    if not verification.ok:
                        st.error("Could not verify the login session.")
                        return

                except requests.RequestException as exc:
                    st.error(f"Connection failed: {exc}")
                    return

                st.session_state.api_url = clean_url
                st.session_state.api_session = session
                st.session_state.authenticated = True
                st.rerun()


# --------------------------------------------------
# Data helpers
# --------------------------------------------------

def records_from(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]

    if isinstance(payload, dict):
        for key in (
            "data", "items", "results", "meters",
            "transformers", "records", "rows"
        ):
            value = payload.get(key)

            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]

            if isinstance(value, dict):
                result = records_from(value)
                if result:
                    return result

    return []


def as_frame(payload):
    rows = records_from(payload)
    return pd.json_normalize(rows) if rows else pd.DataFrame()


def find_col(df, terms):
    for col in df.columns:
        normalized = str(col).lower().replace("_", "").replace(" ", "")
        if any(term in normalized for term in terms):
            return col
    return None


def get_value(row, names):
    normalized = {
        str(k).lower().replace("_", "").replace(" ", ""): v
        for k, v in row.items()
    }

    for name in names:
        key = name.lower().replace("_", "").replace(" ", "")
        if key in normalized:
            return normalized[key]

    return None


def extract_coordinates(payload):
    candidates = []

    if isinstance(payload, dict):
        candidates.append(payload)

        for value in payload.values():
            if isinstance(value, dict):
                candidates.append(value)
            elif isinstance(value, list):
                candidates.extend(
                    x for x in value if isinstance(x, dict)
                )

    for item in candidates:
        lat = get_value(item, ("latitude", "lat"))
        lon = get_value(item, ("longitude", "lon", "lng"))

        try:
            lat = float(lat)
            lon = float(lon)

            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon
        except (TypeError, ValueError):
            continue

    return None, None


def show_hero(title, subtitle):
    st.markdown(
        f"""
        <div class="hero">
            <div class="eyebrow">DISTRIBUTION NETWORK · OPERATIONS</div>
            <h1>{title}</h1>
            <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def style_chart(fig, height=350):
    fig.update_layout(
        height=height,
        margin=dict(l=15, r=15, t=35, b=15),
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(family="DM Sans", color="#34445c"),
        legend_title_text="",
        hovermode="x unified",
    )

    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#edf1f6", zeroline=False)

    return fig


# --------------------------------------------------
# Consumption charts
# --------------------------------------------------

def render_energy(payload):
    df = as_frame(payload)

    st.subheader("Consumption history")

    if df.empty:
        st.info("No consumption readings were returned.")
        with st.expander("Raw response"):
            st.json(payload)
        return

    time_col = find_col(
        df,
        ("timestamp", "datetime", "date", "time"),
    )

    if not time_col:
        st.dataframe(df, use_container_width=True, hide_index=True)
        return

    df[time_col] = pd.to_datetime(
        df[time_col],
        errors="coerce",
        dayfirst=True,
    )

    numeric_cols = []

    for col in df.columns:
        if col == time_col:
            continue

        converted = pd.to_numeric(df[col], errors="coerce")

        if converted.notna().any():
            df[col] = converted
            numeric_cols.append(col)

    df = df.dropna(subset=[time_col]).sort_values(time_col)

    if df.empty or not numeric_cols:
        st.dataframe(df, use_container_width=True, hide_index=True)
        return

    kwh = find_col(df, ("kwh",))
    kvah = find_col(df, ("kvah",))

    m1, m2, m3 = st.columns(3)

    if kwh:
        m1.metric("Latest kWh", f"{df[kwh].iloc[-1]:,.2f}")

    if kvah:
        m2.metric("Latest kVAh", f"{df[kvah].iloc[-1]:,.2f}")

    m3.metric("Total readings", f"{len(df):,}")

    defaults = [c for c in (kwh, kvah) if c]

    selected = st.multiselect(
        "Select metrics",
        numeric_cols,
        default=defaults or numeric_cols[:2],
    )

    if selected:
        chart_data = df[[time_col] + selected].melt(
            id_vars=time_col,
            var_name="Metric",
            value_name="Reading",
        )

        fig = px.line(
            chart_data,
            x=time_col,
            y="Reading",
            color="Metric",
            markers=False,
        )

        fig.update_traces(line_width=2.2)

        st.plotly_chart(
            style_chart(fig, 400),
            use_container_width=True,
        )

    # Simple voltage screening. This is indicative, not a fault diagnosis.
    voltage_col = find_col(df, ("voltage", "vr", "vy", "vb"))

    if voltage_col:
        voltage = pd.to_numeric(
            df[voltage_col],
            errors="coerce",
        ).dropna()

        if not voltage.empty:
            low = int((voltage < 200).sum())
            high = int((voltage > 250).sum())

            st.subheader("Voltage screening")

            a, b, c = st.columns(3)
            a.metric("Readings checked", len(voltage))
            b.metric("Below 200 V", low)
            c.metric("Above 250 V", high)

            if low or high:
                st.warning(
                    "Some readings fall outside the illustrative "
                    "200–250 V screening band. Confirm the applicable "
                    "standard before treating these as faults."
                )

    with st.expander("View readings table"):
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            height=330,
        )


# --------------------------------------------------
# Overview dashboard
# --------------------------------------------------

def overview_page():
    show_hero(
        "Grid intelligence, at a glance.",
        "Monitor meters, installation status and transformer capacity.",
    )

    try:
        with st.spinner("Loading network overview..."):
            meter_payload = api_request(
                "GET", "/api/v1/meters",
                params={"page": 1},
            )

            transformer_payload = api_request(
                "GET", "/api/v1/transformers",
                params={"page": 1},
            )

    except RuntimeError as exc:
        st.error(str(exc))
        return

    meter_df = as_frame(meter_payload)
    transformer_df = as_frame(transformer_payload)

    meter_rows = records_from(meter_payload)
    transformer_rows = records_from(transformer_payload)

    total = None

    if isinstance(meter_payload, dict):
        total = meter_payload.get("total") or meter_payload.get("count")

    if total is None:
        total = len(meter_rows)

    status_col = find_col(
        meter_df,
        ("status", "installationstatus"),
    )

    statuses = (
        meter_df[status_col].fillna("").astype(str).str.lower()
        if status_col else pd.Series(dtype=str)
    )

    installed = int(statuses.str.contains("install", regex=False).sum())
    faulty = int(statuses.str.contains("fault", regex=False).sum())

    k1, k2, k3, k4 = st.columns(4)

    k1.metric("Total meters", f"{int(total):,}")
    k2.metric("Installed", f"{installed:,}")
    k3.metric("Faulty", f"{faulty:,}")
    k4.metric("Transformers", f"{len(transformer_rows):,}")

    left, right = st.columns([1, 1.2], gap="large")

    with left:
        st.subheader("Installation status")

        if not statuses.empty and (statuses != "").any():
            counts = (
                statuses[statuses != ""]
                .str.title()
                .value_counts()
                .rename_axis("Status")
                .reset_index(name="Meters")
            )

            fig = px.pie(
                counts,
                names="Status",
                values="Meters",
                hole=0.68,
                color_discrete_sequence=[
                    "#347da8", "#e5a34e",
                    "#d36f70", "#91a9bd",
                ],
            )

            fig.update_traces(
                textposition="inside",
                textinfo="percent",
            )

            st.plotly_chart(
                style_chart(fig, 340),
                use_container_width=True,
            )
        else:
            st.info("No installation status data available.")

    with right:
        st.subheader("Transformer capacity")

        capacity_col = find_col(
            transformer_df,
            ("capacity", "kva"),
        )

        name_col = find_col(
            transformer_df,
            ("name", "code"),
        )

        if capacity_col:
            chart_df = transformer_df.copy()
            chart_df[capacity_col] = pd.to_numeric(
                chart_df[capacity_col],
                errors="coerce",
            )

            chart_df = chart_df.dropna(
                subset=[capacity_col]
            ).sort_values(capacity_col)

            if not chart_df.empty:
                fig = px.bar(
                    chart_df,
                    x=capacity_col,
                    y=name_col or chart_df.index,
                    orientation="h",
                    labels={
                        capacity_col: "Capacity (kVA)",
                        name_col: "Transformer",
                    },
                )

                fig.update_traces(
                    marker_color="#347da8",
                    marker_line_width=0,
                )

                st.plotly_chart(
                    style_chart(fig, 340),
                    use_container_width=True,
                )
            else:
                st.info("No numeric capacity data available.")
        else:
            st.info("Capacity information is not available.")

    st.subheader("Recent meter records")

    if not meter_df.empty:
        st.dataframe(
            meter_df.head(8),
            use_container_width=True,
            hide_index=True,
        )

    st.caption(
        "Figures are based on the records returned by the current API page."
    )


# --------------------------------------------------
# Meter explorer
# --------------------------------------------------

def meter_explorer_page():
    show_hero(
        "Meter explorer",
        "Search meters and inspect their location and readings.",
    )

    with st.form("meter_search"):
        c1, c2, c3 = st.columns([5, 1, 1])

        query = c1.text_input(
            "Search",
            placeholder="Meter number or serial number",
        )

        page = c2.number_input(
            "Page",
            min_value=1,
            max_value=10000,
            value=1,
        )

        submitted = c3.form_submit_button(
            "Search",
            type="primary",
            use_container_width=True,
        )

    if submitted or "meter_payload" not in st.session_state:
        try:
            st.session_state.meter_payload = api_request(
                "GET",
                "/api/v1/meters",
                params={"q": query, "page": int(page)},
            )
        except RuntimeError as exc:
            st.error(str(exc))
            return

    df = as_frame(st.session_state.meter_payload)

    if df.empty:
        st.info("No meters found.")
        return

    status_col = find_col(
        df,
        ("status", "installationstatus"),
    )

    if status_col:
        choices = sorted(
            df[status_col].dropna().astype(str).unique()
        )

        selected = st.multiselect(
            "Filter by installation status",
            choices,
            default=choices,
        )

        df = df[df[status_col].astype(str).isin(selected)]

    st.caption(f"{len(df)} records displayed")

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=380,
    )

    id_col = find_col(
        df,
        ("meterid", "meternumber"),
    )

    if not id_col:
        st.info("Could not identify the meter ID field.")
        return

    meter_ids = df[id_col].dropna().astype(str).tolist()

    if not meter_ids:
        return

    st.subheader("Meter details")

    selected_id = st.selectbox(
        "Select a meter",
        meter_ids,
    )

    c1, c2 = st.columns(2)

    with c1:
        if st.button("View location", use_container_width=True):
            try:
                st.session_state.geo_payload = api_request(
                    "GET",
                    f"/api/v1/meters/{selected_id}/geo",
                )
                st.session_state.geo_meter_id = selected_id
            except RuntimeError as exc:
                st.error(str(exc))

    with c2:
        if st.button("View consumption", use_container_width=True):
            try:
                st.session_state.selected_energy = api_request(
                    "GET",
                    f"/api/v1/meters/{selected_id}/energy",
                )
                st.session_state.energy_meter_id = selected_id
            except RuntimeError as exc:
                st.error(str(exc))

    if st.session_state.get("geo_meter_id") == selected_id:
        geo = st.session_state.geo_payload
        lat, lon = extract_coordinates(geo)

        st.markdown("#### Meter location")

        if lat is not None:
            map_df = pd.DataFrame([{
                "meter_id": selected_id,
                "lat": lat,
                "lon": lon,
            }])

            deck = pdk.Deck(
                layers=[
                    pdk.Layer(
                        "ScatterplotLayer",
                        data=map_df,
                        get_position="[lon, lat]",
                        get_radius=90,
                        get_fill_color=[52, 125, 168, 220],
                        pickable=True,
                    ),
                ],
                initial_view_state=pdk.ViewState(
                    latitude=lat,
                    longitude=lon,
                    zoom=14,
                ),
                map_style="https://basemaps.cartocdn.com/gl/positron-gl-style",
                tooltip={"text": "Meter: {meter_id}"},
            )

            st.pydeck_chart(deck, use_container_width=True)
        else:
            st.info("No valid latitude/longitude found.")

        with st.expander("Location data"):
            st.json(geo)

    if st.session_state.get("energy_meter_id") == selected_id:
        render_energy(st.session_state.selected_energy)


# --------------------------------------------------
# Consumption page
# --------------------------------------------------

def consumption_page():
    show_hero(
        "Consumption analytics",
        "Explore meter readings and identify unusual patterns.",
    )

    meter_id = st.text_input(
        "Meter ID",
        value=st.session_state.get("last_meter_id", ""),
    )

    if st.button(
        "Load readings",
        type="primary",
        disabled=not meter_id.strip(),
    ):
        try:
            with st.spinner("Loading readings..."):
                st.session_state.energy_payload = api_request(
                    "GET",
                    f"/api/v1/meters/{meter_id.strip()}/energy",
                )

                st.session_state.last_meter_id = meter_id.strip()

        except RuntimeError as exc:
            st.error(str(exc))

    if st.session_state.get("energy_payload") is not None:
        render_energy(st.session_state.energy_payload)


# --------------------------------------------------
# Network map
# --------------------------------------------------

def network_map_page():
    show_hero(
        "Network map",
        "Explore the geographic distribution of your meters.",
    )

    st.info(
        "Coordinates are loaded from the meter location endpoint. "
        "Start with a small page to limit upstream requests."
    )

    page = st.number_input(
        "Meter page",
        min_value=1,
        max_value=10000,
        value=1,
        key="network_page",
    )

    if st.button("Load network map", type="primary"):
        try:
            with st.spinner("Fetching meter locations..."):
                payload = api_request(
                    "GET",
                    "/api/v1/meters",
                    params={"page": int(page)},
                )

                rows = records_from(payload)
                points = []

                progress = st.progress(0)

                for i, row in enumerate(rows):
                    meter_id = get_value(
                        row,
                        ("meter_id", "meter", "id", "meter_number"),
                    )

                    if meter_id:
                        try:
                            geo = api_request(
                                "GET",
                                f"/api/v1/meters/{meter_id}/geo",
                            )

                            lat, lon = extract_coordinates(geo)

                            if lat is not None:
                                points.append({
                                    "meter_id": str(meter_id),
                                    "lat": lat,
                                    "lon": lon,
                                })

                        except RuntimeError:
                            pass

                    progress.progress(
                        (i + 1) / max(len(rows), 1)
                    )

                st.session_state.network_points = points

        except RuntimeError as exc:
            st.error(str(exc))
            return

    points = st.session_state.get("network_points", [])

    if not points:
        st.caption("Load a meter page to display its locations.")
        return

    df = pd.DataFrame(points)

    c1, c2 = st.columns(2)
    c1.metric("Mapped meters", len(df))
    c2.metric(
        "Unique locations",
        len(df[["lat", "lon"]].drop_duplicates()),
    )

    deck = pdk.Deck(
        layers=[
            pdk.Layer(
                "ScatterplotLayer",
                data=df,
                get_position="[lon, lat]",
                get_radius=55,
                get_fill_color=[52, 125, 168, 190],
                get_line_color=[255, 255, 255, 220],
                line_width_min_pixels=1,
                pickable=True,
            ),
        ],
        initial_view_state=pdk.ViewState(
            latitude=float(df["lat"].median()),
            longitude=float(df["lon"].median()),
            zoom=11,
            pitch=30,
        ),
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style",
        tooltip={"text": "Meter: {meter_id}"},
    )

    st.pydeck_chart(deck, use_container_width=True)

    with st.expander("Mapped coordinates"):
        st.dataframe(df, use_container_width=True, hide_index=True)


# --------------------------------------------------
# Transformers
# --------------------------------------------------

def transformers_page():
    show_hero(
        "Distribution transformers",
        "Compare capacity and explore the transformer directory.",
    )

    page = st.number_input(
        "Page",
        min_value=1,
        max_value=10000,
        value=1,
        key="transformer_page",
    )

    if st.button("Load transformers", type="primary") or (
        "transformer_payload" not in st.session_state
    ):
        try:
            st.session_state.transformer_payload = api_request(
                "GET",
                "/api/v1/transformers",
                params={"page": int(page)},
            )
        except RuntimeError as exc:
            st.error(str(exc))
            return

    df = as_frame(st.session_state.transformer_payload)

    if df.empty:
        st.info("No transformer records found.")
        return

    capacity_col = find_col(df, ("capacity", "kva"))
    name_col = find_col(df, ("name", "code"))

    if capacity_col:
        df[capacity_col] = pd.to_numeric(
            df[capacity_col],
            errors="coerce",
        )

        valid = df.dropna(
            subset=[capacity_col]
        ).sort_values(capacity_col)

        if not valid.empty:
            c1, c2 = st.columns(2)

            c1.metric("Transformers on page", len(df))
            c2.metric(
                "Combined listed capacity",
                f"{valid[capacity_col].sum():,.0f} kVA",
            )

            fig = px.bar(
                valid,
                x=capacity_col,
                y=name_col or valid.index,
                orientation="h",
                labels={
                    capacity_col: "Capacity (kVA)",
                    name_col: "Transformer",
                },
                color=capacity_col,
                color_continuous_scale=[
                    "#dceaf3",
                    "#286f9d",
                ],
            )

            st.plotly_chart(
                style_chart(fig, max(350, min(650, len(valid) * 32))),
                use_container_width=True,
            )

    st.subheader("Transformer directory")

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=420,
    )


# --------------------------------------------------
# Navigation
# --------------------------------------------------

def dashboard():
    with st.sidebar:
        st.markdown("## ⚡ FLOCK ENERGY")
        st.caption("METER OPERATIONS")
        st.divider()

        page = st.radio(
            "WORKSPACE",
            [
                "Overview",
                "Meter explorer",
                "Consumption",
                "Network map",
                "Transformers",
            ],
        )

        st.divider()

        if st.button("Sign out", use_container_width=True):
            try:
                api_request("POST", LOGOUT_PATH)
            except RuntimeError:
                pass

            st.session_state.clear()
            st.rerun()

    if page == "Overview":
        overview_page()
    elif page == "Meter explorer":
        meter_explorer_page()
    elif page == "Consumption":
        consumption_page()
    elif page == "Network map":
        network_map_page()
    elif page == "Transformers":
        transformers_page()


# --------------------------------------------------
# Main
# --------------------------------------------------

if not st.session_state.get("authenticated", False):
    login_view()
else:
    dashboard()
