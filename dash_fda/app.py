import os
import pandas as pd
import dash_core_components as dcc
import dash_html_components as html
import dash_table_experiments as dt
import plotly.plotly as py
import plotly.graph_objs as go
from functools import partial
from flask import Flask
from flask_caching import Cache
from dash import Dash
from dash.dependencies import Input, Output, State
from dotenv import load_dotenv
from dash_fda.utils import get_results, get_meta, create_intermediate_df, unjsonify
from dash_fda.exceptions import ImproperlyConfigured


def create_years(df):
    # In order to group by week, year, etc later on, we need to create a
    # datetime variable now and set it as an index (because DataFrame.resample
    # needs a DatetimeIndex)
    df["date"] = pd.to_datetime(df["time"])
    df.set_index(df["date"], inplace=True)
    # we don't need the original 'time' column any longer, so we can drop it.
    df.drop(["time"], axis=1, inplace=True)

    dfr = df.resample("Y").sum()
    dfr["year"] = dfr.index.strftime("%Y")
    grouped = dfr.groupby("year")
    dframe = grouped.sum()
    return dframe


def create_months(df):
    # In order to group by week, year, etc later on, we need to create a
    # datetime variable now and set it as an index (because DataFrame.resample
    # needs a DatetimeIndex)
    df["date"] = pd.to_datetime(df["time"])
    df.set_index(df["date"], inplace=True)
    # we don't need the original 'time' column any longer, so we can drop it.
    df.drop(["time"], axis=1, inplace=True)

    dfr = df.resample("M").sum()
    dfr["month"] = dfr.index.strftime("%B")
    # don't sort alphabetically
    grouped = dfr.groupby("month", sort=False)
    dframe = grouped.sum()

    # We now have a DataFrame grouped by month of the year, but not necessarily
    # sorted as we would like to have it: [January, February, ..., December].
    # We can fix this in 4 steps:
    # 1) reset index (in place): 'month' becomes a new column in the DataFrame
    dframe.reset_index(inplace=True)
    # 2) create new column to sort (in place) the records in the DataFrame
    custom_dict = {
        "January": 0,
        "February": 1,
        "March": 2,
        "April": 3,
        "May": 4,
        "June": 5,
        "July": 6,
        "August": 7,
        "September": 8,
        "October": 9,
        "November": 10,
        "December": 11,
    }
    dframe["rank"] = dframe["month"].map(custom_dict)
    dframe.sort_values(by="rank", inplace=True)
    # 3) drop (in place) the column that we have just used for sorting
    dframe.drop(["rank"], axis=1, inplace=True)
    # 4) restore the original index (in place)
    dframe.set_index("month", inplace=True)
    return dframe


def create_months_box(df):
    # In order to group by week, year, etc later on, we need to create a
    # datetime variable now and set it as an index (because DataFrame.resample
    # needs a DatetimeIndex)
    df["date"] = pd.to_datetime(df["time"])
    df.set_index(df["date"], inplace=True)
    # we don't need the original 'time' column any longer, so we can drop it.
    df.drop(["time"], axis=1, inplace=True)

    dfr = df.resample("M").sum()
    dfr["month"] = dfr.index.strftime("%B")

    months = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    dataframes = list()
    for m in months:
        arr = dfr[dfr.month == m]["count"].values
        dff = pd.DataFrame({m: arr})
        dataframes.append(dff)

    dframe = pd.concat(dataframes, axis=1)
    return dframe


def create_days(df):
    # In order to group by week, year, etc later on, we need to create a
    # datetime variable now and set it as an index (because DataFrame.resample
    # needs a DatetimeIndex)
    df["date"] = pd.to_datetime(df["time"])
    df.set_index(df["date"], inplace=True)
    # we don't need the original 'time' column any longer, so we can drop it.
    df.drop(["time"], axis=1, inplace=True)

    dfr = df.resample("D").sum()
    dfr["day"] = dfr.index.strftime("%A")
    # don't sort alphabetically
    grouped = dfr.groupby("day", sort=False)
    dframe = grouped.sum()

    # We now have a DataFrame grouped by weekday, but not necessarily sorted as
    # we would like to have it: [Monday, Tuesday, ..., Sunday].
    # We can fix this in 4 steps:
    # 1) reset index (in place): 'day' becomes a new column in the DataFrame
    dframe.reset_index(inplace=True)
    # 2) create new column to sort (in place) the records in the DataFrame
    custom_dict = {
        "Monday": 0,
        "Tuesday": 1,
        "Wednesday": 2,
        "Thursday": 3,
        "Friday": 4,
        "Saturday": 5,
        "Sunday": 6,
    }
    dframe["rank"] = dframe["day"].map(custom_dict)
    dframe.sort_values(by="rank", inplace=True)
    # 3) drop (in place) the column that we have just used for sorting
    dframe.drop(["rank"], axis=1, inplace=True)
    # 4) restore the original index (in place)
    dframe.set_index("day", inplace=True)
    return dframe


external_js = []

external_css = [
    # dash stylesheet
    "https://codepen.io/chriddyp/pen/bWLwgP.css",
    "https://fonts.googleapis.com/css?family=Lobster|Raleway",
]

if "DYNO" in os.environ:
    # the app is on Heroku
    debug = False
    # google analytics with the tracking ID for this app
    # external_js.append('https://codepen.io/jackdbd/pen/rYmdLN.js')
else:
    debug = True
    dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
    load_dotenv(dotenv_path)

py.sign_in(os.environ["PLOTLY_USERNAME"], os.environ["PLOTLY_API_KEY"])
openFDA = "https://api.fda.gov/"
api_endpoint = "device/event.json?"
api_key = os.environ.get("OPEN_FDA_API_KEY")
if api_key is None:
    raise ImproperlyConfigured("openFDA API KEY not set in .env")

app_name = "Dash FDA"
server = Flask(app_name)
server.secret_key = os.environ.get("SECRET_KEY")
if server.secret_key is None:
    raise ImproperlyConfigured("Flask SECRET KEY not set in .env")
app = Dash(name=app_name, server=server, csrf_protect=False)

cache = Cache(
    app.server,
    config={
        "CACHE_TYPE": "filesystem",
        "CACHE_DIR": "cache",
        "CACHE_THRESHOLD": 10,
        "CACHE_DEFAULT_TIMEOUT": 30,
    },
)
# app.config.supress_callback_exceptions = True


url_prefix = "{openFDA}{api_endpoint}api_key={api_key}".format(
    openFDA=openFDA, api_endpoint=api_endpoint, api_key=api_key
)

initial_url = "{}&count=date_of_event".format(url_prefix)
initial_results = get_results(initial_url)

theme = {
    "font-family": "Raleway",
    # 'font-family': 'Lobster',
    # 'background-color': '#787878',
    "background-color": "#e0e0e0",
}


def create_box(df, column):
    box = go.Box(name=column, y=df[column].values, boxmean=True)
    return box


def create_header():
    header_style = {"background-color": theme["background-color"], "padding": "1.5rem"}
    header = html.Header(html.H1(children=app_name, style=header_style))
    return header


def create_content():
    content = html.Div(
        children=[
            # range slider with start date and end date
            html.Div(
                children=[
                    dcc.RangeSlider(
                        id="year-slider",
                        min=1991,
                        max=2017,
                        value=[2010, 2015],
                        marks={(i): "{}".format(i) for i in range(1991, 2017, 2)},
                    )
                ],
                style={"margin-bottom": 20},
            ),
            # box plot
            html.Div(children=[dcc.Graph(id="box-plot-month")]),
            html.Hr(),
            # line charts
            html.Div(
                children=[
                    dcc.Graph(id="line-chart-year"),
                    dcc.Graph(id="line-chart-month"),
                    dcc.Graph(id="line-chart-day"),
                ]
            ),
            html.Hr(),
            # pie charts
            html.Div(
                children=[
                    html.Div(dcc.Graph(id="pie-event"), className="six columns"),
                    html.Div(dcc.Graph(id="pie-device"), className="six columns"),
                ],
                className="row",
                style={"margin-bottom": 20},
            ),
            html.Hr(),
            # date picker with start date and end date
            # html.Div(
            #     children=[
            #         dcc.DatePickerRange(
            #             id='date-picker-range',
            #             calendar_orientation='horizontal',
            #             clearable=True,
            #             display_format='DD/MM/YYYY',
            #             start_date=datetime(1991, 1, 2),
            #             # start_date_placeholder_text='Select a date!',
            #             end_date=datetime.now(),
            #             # end_date_placeholder_text='Select a date!',
            #             min_date_allowed='1991-01-01',
            #         ),
            #     ],
            #     className='five columns',
            # ),
            html.Div(
                children=[
                    # medical device label+input
                    html.Div(
                        children=[
                            html.Label("Device"),
                            dcc.Input(
                                id="medical-device-input",
                                placeholder="E.g. x-ray",
                                type="text",
                                value="",
                            ),
                        ],
                        className="four columns",
                    ),
                    # manufacturer label+dropdown
                    html.Div(
                        children=[
                            html.Label("Manufacturer"),
                            dcc.Dropdown(
                                id="manufacturer-dropdown",
                                options=[
                                    {"label": "Covidien", "value": "COVIDIEN"},
                                    {"label": "Esaote", "value": "ESAOTE"},
                                    {"label": "Dräger", "value": "DRAEGER"},
                                    {
                                        "label": "GE Healthcare",
                                        "value": "GE+Healthcare",
                                    },
                                    {
                                        "label": "Medtronic",
                                        "value": "MEDTRONIC+MINIMED",
                                    },
                                    {"label": "Zimmer", "value": "ZIMMER+INC."},
                                    {
                                        "label": "Baxter",
                                        "value": "BAXTER+HEALTHCARE+PTE.+LTD.",
                                    },
                                    {
                                        "label": "Smiths Medical",
                                        "value": "SMITHS+MEDICAL+MD+INC.",
                                    },
                                ],
                                # multi=True,
                                value="GE+Healthcare",
                            ),
                        ],
                        className="four columns",
                    ),
                    # button
                    html.Div(
                        children=[
                            html.Button(
                                "Submit", id="button", style={"margin-top": "1em"}
                            )
                        ],
                        className="two columns offset-by-two",
                    ),
                ],
                className="row",
            ),
            # table with dash_table_experiments
            dt.DataTable(
                id="table-fda",
                rows=initial_results,
                filterable=True,
                sortable=True,
                # selected_row_indices=[],
            ),
            html.Hr(),
        ],
        id="content",
        style={"width": "100%", "height": "100%"},
    )
    return content


def create_footer():
    footer_style = {"background-color": theme["background-color"], "padding": "0.5rem"}
    p0 = html.P(
        children=[
            html.Span("Built with "),
            html.A(
                "Plotly Dash", href="https://github.com/plotly/dash", target="_blank"
            ),
        ]
    )
    p1 = html.P(
        children=[
            html.Span("Data from the "),
            html.A("openFDA API", href=openFDA, target="_blank"),
        ]
    )
    meta = get_meta(initial_url)
    disclaimer = meta["disclaimer"]
    div = html.Div([p0, p1, disclaimer])
    # last_updated = meta['last_updated']
    footer = html.Footer(children=div, style=footer_style)
    return footer


def serve_layout():
    layout = html.Div(
        children=[
            # Hidden div inside the app that stores the intermediate value
            html.Div(id="intermediate-value", style={"display": "none"}),
            create_header(),
            create_content(),
            create_footer(),
        ],
        className="container",
        style={"font-family": theme["font-family"]},
    )
    return layout


app.layout = serve_layout
for js in external_js:
    app.scripts.append_script({"external_url": js})
for css in external_css:
    app.css.append_css({"external_url": css})


@app.callback(
    output=Output("table-fda", "rows"),
    inputs=[Input("button", "n_clicks")],
    state=[
        State("year-slider", "value"),
        State("manufacturer-dropdown", "value"),
        State("medical-device-input", "value"),
    ],
)
@cache.memoize(timeout=30)  # in seconds
def update_table(n_clicks, year_range, manufacturer, device):
    start = "{}-01-01".format(year_range[0])
    end = "{}-12-31".format(year_range[1])
    url = (
        "{url_prefix}&search=date_received:[{date_start}+TO+{date_end}]+"
        "AND+device.manufacturer_d_name:{manufacturer}+"
        "AND+device.generic_name:{device}&limit={num}&skip=0".format(
            url_prefix=url_prefix,
            date_start=start,
            date_end=end,
            manufacturer=manufacturer,
            device=device,
            num=100,
        )
    )
    results = get_results(url)

    # TODO: it seems that most of the info is in the mdr_text field (a list)
    rows = list()
    for res in results:
        if len(res["mdr_text"]) > 0:
            yes_or_no = "Yes"
        else:
            yes_or_no = "No"
        row = {
            "Event type": res["event_type"],
            "Location": res["event_location"],
            "Reporter": res["reporter_occupation_code"],
            "Has MDR Text": yes_or_no,
        }
        rows.append(row)
    return rows


@app.callback(
    output=Output("intermediate-value", "children"),
    inputs=[Input("year-slider", "value")],
)
# @cache.memoize(timeout=30)  # in seconds
def update_intermediate_value(year_range):
    start = "{}-01-01".format(year_range[0])
    end = "{}-12-31".format(year_range[1])

    url_a = (
        "{url_prefix}&search=date_of_event:[{date_start}+TO+{date_end}]"
        "&count=date_of_event".format(
            url_prefix=url_prefix, date_start=start, date_end=end
        )
    )
    df_a = create_intermediate_df(url_a)

    url_b = (
        "{url_prefix}&search=date_received:[{date_start}+TO+{date_end}]"
        "&count=date_received".format(
            url_prefix=url_prefix, date_start=start, date_end=end
        )
    )
    df_b = create_intermediate_df(url_b)

    children = [
        html.Div(df_a.to_json(), id="json-date-of-event"),
        html.Div(df_b.to_json(), id="json-date-received"),
    ]
    return children


@app.callback(
    output=Output("pie-event", "figure"), inputs=[Input("year-slider", "value")]
)
# @cache.memoize(timeout=30)  # in seconds (pickle.dump fails)
def update_pie_event(year_range):
    start = "{}-01-01".format(year_range[0])
    end = "{}-12-31".format(year_range[1])
    url = (
        "{url_prefix}&search=date_received:[{date_start}+TO+{date_end}]"
        "&count=event_type".format(
            url_prefix=url_prefix, date_start=start, date_end=end
        )
    )
    results = get_results(url)
    labels = [r["term"] for r in results]
    values = [r["count"] for r in results]

    data = [
        go.Pie(
            name="Event Type",
            values=values,
            labels=labels,
            hoverinfo="label + percent + name",
            hole=0.45,
            # showlegend=False,
        )
    ]
    layout = go.Layout(
        title="Adverse Event Type",
        autosize=True,
        hovermode="closest",
        font=dict(family=theme["font-family"], color="#777777", size=24),
        # margin=go.Margin(l=0, r=0, t=45, b=10),
    )
    figure = go.Figure(data=data, layout=layout)
    return figure


# @cache.memoize()  # if placed here, it seems to work
@app.callback(
    output=Output("pie-device", "figure"), inputs=[Input("year-slider", "value")]
)
# @cache.memoize()  # if placed here, pickle.dump fails
def update_pie_device(year_range):
    start = "{}-01-01".format(year_range[0])
    end = "{}-12-31".format(year_range[1])
    url = (
        "{url_prefix}&search=date_received:[{date_start}+TO+{date_end}]"
        "&count=device.openfda.device_class".format(
            url_prefix=url_prefix, date_start=start, date_end=end
        )
    )
    results = get_results(url)
    labels = [r["term"] for r in results]
    values = [r["count"] for r in results]

    data = [
        go.Pie(
            name="Device Class",
            values=values,
            labels=labels,
            hoverinfo="label + percent + name",
            hole=0.45,
        )
    ]
    layout = go.Layout(
        title="Medical Device Class",
        autosize=True,
        hovermode="closest",
        font=dict(family=theme["font-family"], color="#777777", size=24),
    )
    figure = go.Figure(data=data, layout=layout)
    return figure


@app.callback(
    output=Output("line-chart-year", "figure"),
    inputs=[Input("intermediate-value", "children")],
)
def update_line_chart_by_year(jsonified_divs):
    df_a = unjsonify(jsonified_divs, "json-date-of-event")
    df_a.rename(columns={"count": "A"}, inplace=True)
    df_b = unjsonify(jsonified_divs, "json-date-received")
    df_b.rename(columns={"count": "B"}, inplace=True)

    df_merged = pd.merge(df_a, df_b, on="time")
    df = create_years(df_merged)

    data = [
        go.Scatter(
            x=df.index.values, y=df.A, mode="lines", name="Onset of the adverse event"
        ),
        go.Scatter(
            x=df.index.values,
            y=df["B"],
            mode="lines+markers",
            name="Report received by FDA",
        ),
    ]
    layout = go.Layout(
        title="Adverse event reports by Year",
        font=dict(family=theme["font-family"], color="#777777"),
    )
    figure = go.Figure(data=data, layout=layout)
    return figure


@app.callback(
    output=Output("line-chart-month", "figure"),
    inputs=[Input("intermediate-value", "children")],
)
def update_line_chart_by_month(jsonified_divs):
    df_a = unjsonify(jsonified_divs, "json-date-of-event")
    df_a.rename(columns={"count": "A"}, inplace=True)
    df_b = unjsonify(jsonified_divs, "json-date-received")
    df_b.rename(columns={"count": "B"}, inplace=True)

    df_merged = pd.merge(df_a, df_b, on="time")
    df = create_months(df_merged)

    data = [
        go.Scatter(
            x=df.index.values, y=df.A, mode="lines", name="Onset of the adverse event"
        ),
        go.Scatter(
            x=df.index.values,
            y=df["B"],
            mode="lines+markers",
            name="Report received by FDA",
        ),
    ]
    layout = go.Layout(
        title="Adverse event reports by Month",
        font=dict(family=theme["font-family"], color="#777777"),
    )
    figure = go.Figure(data=data, layout=layout)
    return figure


@app.callback(
    output=Output("box-plot-month", "figure"),
    inputs=[Input("intermediate-value", "children")],
)
def update_box_plot_by_month(jsonified_divs):
    df_b = unjsonify(jsonified_divs, "json-date-received")
    df = create_months_box(df_b)

    func = partial(create_box, df)
    boxes = list(map(func, df.columns))

    data = boxes
    layout = go.Layout(
        title="Adverse event reports received by Month",
        font=dict(family=theme["font-family"], color="#777777"),
    )
    figure = go.Figure(data=data, layout=layout)
    return figure


@app.callback(
    output=Output("line-chart-day", "figure"),
    inputs=[Input("intermediate-value", "children")],
)
def update_line_chart_by_day(jsonified_divs):
    df_a = unjsonify(jsonified_divs, "json-date-of-event")
    df_a.rename(columns={"count": "A"}, inplace=True)
    df_b = unjsonify(jsonified_divs, "json-date-received")
    df_b.rename(columns={"count": "B"}, inplace=True)

    df_merged = pd.merge(df_a, df_b, on="time")
    df = create_days(df_merged)

    data = [
        go.Scatter(
            x=df.index.values, y=df.A, mode="lines", name="Onset of the adverse event"
        ),
        go.Scatter(
            x=df.index.values,
            y=df["B"],
            mode="lines+markers",
            name="Report received by FDA",
        ),
    ]
    layout = go.Layout(
        title="Adverse event reports by Day",
        font=dict(family=theme["font-family"], color="#777777"),
    )
    figure = go.Figure(data=data, layout=layout)
    return figure


if __name__ == "__main__":
    cache.clear()
    port = int(os.environ.get("PORT", 5000))
    app.run_server(debug=debug, port=port, threaded=True)
