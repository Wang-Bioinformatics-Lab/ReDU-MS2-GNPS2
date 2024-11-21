import requests
import os
import dash
from dash import dcc, html, dash_table, Input, Output, State, callback_context, Dash
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
import pandas as pd
import re
import math
import sys
import json

from app import app

from utils import _load_redu_sampledata, _metadata_last_modified

def _filter_redu_sampledata(redu_df, filter_query=None):

    print(filter_query, file=sys.stderr, flush=True)

    if filter_query:
        filtering_expressions = filter_query.split(' && ')
        for filter_part in filtering_expressions:
            col_name, operator, value = split_filter_part(filter_part)
            print('col_name, operator, value', file=sys.stderr, flush=True)
            print(col_name, operator, value, file=sys.stderr, flush=True)
            if operator and col_name in redu_df.columns:
                # Apply operator logic as previously defined
                if operator == 'contains':
                    redu_df = redu_df[
                        redu_df[col_name].astype(str).str.contains(value, case=False, na=False, regex=True)]
                if operator == 'scontains':
                    redu_df = redu_df[
                        redu_df[col_name].astype(str).str.contains(value, case=True, na=False, regex=True)]
                elif operator == '=' or operator == 's=':
                    redu_df = redu_df[redu_df[col_name] == value]
                elif operator == '!=' or operator == 's!=':
                    redu_df = redu_df[redu_df[col_name] != value]
                elif operator == '<' or operator == 's<':
                    redu_df = redu_df[
                        pd.to_numeric(redu_df[col_name], errors='coerce') < float(value)]
                elif operator == '<=' or operator == 's<=':
                    redu_df = redu_df[
                        pd.to_numeric(redu_df[col_name], errors='coerce') <= float(value)]
                elif operator == '>' or operator == 's>':
                    redu_df = redu_df[
                        pd.to_numeric(redu_df[col_name], errors='coerce') > float(value)]
                elif operator == '>='  or operator == 's>=':
                    redu_df = redu_df[
                        pd.to_numeric(redu_df[col_name], errors='coerce') >= float(value)]

    return redu_df

    

# Load the data
df_redu = _load_redu_sampledata()

# Define column configurations
default_columns = ["SampleType", "SampleTypeSub1", "NCBITaxonomy", "UBERONBodyPartName", "MassSpectrometer", "USI"]

# All columns in desired order
all_columns_ordered = default_columns + [col for col in df_redu.columns if col not in default_columns]

# Initialize the Dash app with Bootstrap theme
dash_app = dash.Dash(
    name="redu_selection",
    server=app,
    url_base_pathname="/selection/",
    external_stylesheets=[dbc.themes.BOOTSTRAP],
)

dash_app.config.suppress_callback_exceptions = True  # Allow callbacks for components not in the initial layout
dash_app.title = 'ReDU2'


# Determine which columns are hidden by default
hidden_columns = [col for col in all_columns_ordered if col not in default_columns]


# Make logo path
image_url = dash_app.get_asset_url("panReDU_logo.PNG")


# Create the navigation menu with the logo
navbar = dbc.Navbar(
    dbc.Container([
        html.A(
            html.Img(src=dash_app.get_asset_url("panReDU_logo.png"), height="80px", style={"padding-right": "15px"}),
            href="/",
            style={"textDecoration": "none"}
        ),
        dbc.NavbarSimple(
            children=[
                dbc.NavItem(
                    html.A(
                        "Contribute Your Metadata",
                        href="https://deposit.redu.gnps2.org/",
                        target="_blank",
                        className="nav-link",
                        style={"fontSize": "20px", "margin-right": "100px"}
                    )
                ),                
                dbc.NavItem(
                    html.A(
                        "Column Descriptions and Metadata validation",
                        href="https://docs.google.com/spreadsheets/d/10U0xnJUKa_mD0H_9suH1KJAlJD9io9e4chBX8EAHneE/edit?usp=sharing",
                        target="_blank",
                        className="nav-link",
                        style={"fontSize": "20px", "margin-right": "100px"}
                    )
                ),
                dbc.NavItem(
                    html.A(
                        "ReDU Dashboard - Documentation",
                        href="https://wang-bioinformatics-lab.github.io/GNPS2_Documentation/ReDU_overview/",
                        target="_blank",
                        className="nav-link",
                        style={"fontSize": "20px", "margin-right": "100px"}
                    )
                ),
                dbc.NavItem(
                    html.A(
                        "Download Complete ReDU",
                        href="/dump",
                        target="_blank",
                        id="download-complete-link",
                        className="nav-link",
                        style={"fontSize": "20px", "margin-right": "20px"}
                    )
                )
            ],
            color="#e1e8f2",  # Adjusted color to complement the logo
            dark=False,  # Set to False if you choose a light color for better readability
            expand=True,  # This allows the navbar to expand and fill the space
        ),
        dcc.Download(id="download-complete-tsv"),
    ], fluid=True),
    color="#e1e8f2",  # Adjusted color for the navbar background
    dark=False,
)

# Layout for the PanReDU page (Main Dashboard)
panredu_layout = dbc.Container(fluid=True, children=[
    # Main Row for Left Panel and Right Column (Title, Description, Buttons, and Table)
    dbc.Row([
        # Left Panel: Summary Statistics with Padding Above
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H2('Summary Statistics')),
                dbc.CardBody(id="summary-stats")
            ], className='mb-4'),

            html.Div([
                html.H5("Example Filters:"),
                dbc.Button("Human Samples", id="example-filter-human", color="link"),
                html.Br(),
                dbc.Button("Plant Samples", id="example-filter-plant", color="link"),
                html.Br(),
                dbc.Button("Orbitrap Mass Spectrometer", id="example-filter-orbitrap", color="link"),
                html.Br(),
                dbc.Button("Homo sapiens and Mus but no Mus muscuslus", id="example-filter-complex", color="link"),
                html.Br(),
                dbc.Button("Blood Samples from Rattus norvegicus", id="example-filter-multi", color="link"),
                html.Br(),
                dbc.Button("Samples with RP-LC, hydrophobic extraction and MS2 scans", id="example-filter-lipids", color="link"),
            ], className='mb-4'),
        ], width=3, className='mt-4'),  # Add top margin here

        # Right Column with Title, Paragraph, Data Table, and Buttons
        dbc.Col([
            # Title and Paragraph Row
            dbc.Row([
                dbc.Col([
                    html.H1('Pan-ReDU Dashboard', className='text-center my-2'),
                    html.P([
                        'This represents a daily updated metadata table sourcing from the public metabolomics repositories: ',
                        html.Br(),
                        html.A('MetaboLights', href='https://www.ebi.ac.uk/metabolights/', target='_blank',
                               style={'fontSize': '18px'}),
                        ', ',
                        html.A('Metabolomics Workbench', href='https://www.metabolomicsworkbench.org/', target='_blank',
                               style={'fontSize': '18px'}),
                        ', and ',
                        html.A('GNPS',
                               href='https://gnps.ucsd.edu/ProteoSAFe/datasets.jsp#%7B%22query%22%3A%7B%7D%2C%22table_sort_history%22%3A%22createdMillis_dsc%22%2C%22title_input%22%3A%22GNPS%22',
                               target='_blank', style={'fontSize': '18px'}),
                        '.',
                        html.Br(), html.Br(),
                        'Please ',
                        html.A('contribute your data',
                               href='https://deposit.redu.gnps2.org/',
                               target='_blank', style={'fontSize': '18px'}),
                        ' to grow this public resource and bring our field forward!'
                    ], className='text-center mb-4', style={'fontSize': '18px'}),
                ], width=10),

                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader(html.H5("Contributors")),
                        dbc.CardBody([
                            html.P("Yasin El Abiead", className='mb-1'),
                            html.P("Mingxun Wang", className='mb-1'),
                        ])
                    ])
                ], width=2)
            ], align="center"),

            # Buttons Row Above the Data Table
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.H4(['Filter Table'], style={'font-weight': 'bold', 'text-decoration': 'underline', 'text-align': 'center', 'width': '100%', 'margin': '0 auto'}),
                            dbc.Button("Subset Table to mz(X)ML files", id="subset-mzml-button", color="info",
                                       className="mb-2", style={"width": "100%", "height": "23%", "text-align": "center"}),
                            html.P(['Or use the column filters below,..'],
                                   className='text-center mb-4', style={'fontSize': '18px'})
                        ],
                        width=3, className="d-flex flex-column align-items-start justify-content-start",
                        style={"height": "200px"}
                    ),
                    dbc.Col(
                        [
                            html.H4(['Download Filtered Subset'], style={'font-weight': 'bold', 'text-decoration': 'underline', 'text-align': 'center', 'width': '100%', 'margin': '0 auto'}),
                            dbc.Button("ReDU Table", id="download-button", color="warning",
                                       className="mb-2", style={"width": "100%", "height": "23%", "text-align": "center"}),
                            dbc.Button("USIs for Batch Processing/Download", id="USIdownload-button", color="warning",
                                       className="mb-2", style={"width": "100%", "height": "23%", "text-align": "center"},
                                       href="https://github.com/Wang-Bioinformatics-Lab/downloadpublicdata",
                                       target="_blank")
                        ],
                        width=3, className="d-flex flex-column align-items-start justify-content-start",
                        style={"height": "200px"}
                    ),
                    dbc.Col(
                        [
                            html.H4(['Process Selected Files'], style={'font-weight': 'bold', 'text-decoration': 'underline', 'text-align': 'center', 'width': '100%', 'margin': '0 auto'}),
                            dbc.Button("View/Download Raw Data in Browser", id="dashboard-button", color="primary",
                                       className="mb-2", style={"width": "100%", "height": "100%", "text-align": "center"},
                                       href="https://dashboard.gnps2.org/",
                                       target="_blank"),
                            dbc.Button("Molecular Networking/Library Matching", id="mn-button", color="primary",
                                       className="mb-2", style={"width": "100%", "height": "100%", "text-align": "center"},
                                       href="https://gnps2.org/workflowinput?workflowname=classical_networking_workflow",
                                       target="_blank"),
                            dbc.Button("MassQL/Fragmentation Rule Search", id="massql-button", color="primary",
                                       className="mb-2", style={"width": "100%", "height": "100%", "text-align": "center"},
                                       href="https://gnps2.org/workflowinput?workflowname=massql_workflow",
                                       target="_blank")
                        ],
                        width=3, className="d-flex flex-column align-items-start justify-content-around",
                        style={"height": "200px"}
                    ),
                    dbc.Col(
                        [
                            dcc.Loading(
                                id="network-link-button",
                                children=[html.Div([html.Div(id="loading-output-232")])],
                                type="default",
                            )
                        ]
                    )
                ],
                className="mb-2 mt-3"
            ),
            # Data Table Component
            dash_table.DataTable(
                id='data-table',
                columns=[
                    {'name': col, 'id': col, 'hideable': True, 'clearable': True}
                    for col in all_columns_ordered
                ],
                hidden_columns=hidden_columns,
                page_current=0,
                page_size=10,
                page_action='custom',
                row_selectable='multiple',
                filter_action='custom',
                filter_query='',
                filter_options={"placeholder_text": "Filter column..."},
                sort_action='custom',
                sort_mode='multi',
                sort_by=[],
                style_table={'overflowX': 'auto'},
                style_cell={
                    'whiteSpace': 'normal',
                    'height': 'auto',
                    'textAlign': 'left',
                    'userSelect': 'text',
                },
                cell_selectable=False,
            ),
            dbc.Row([
                html.Div(id='page-count', className='mt-2'),  # Page count div
                html.Div(id='rows-remaining', className='mt-2'),  # Rows remaining div
                html.Div(id='dummy-div', style={'display': 'none'})  # Any additional elements if needed
            ], justify="end", className="text-end"),

            # Additional Components if Needed
            dcc.Download(id="download-dataframe-csv"),            

            # Modal for settings popup
            dbc.Modal(
                [
                    dbc.ModalHeader("Subset table to files matching MS2 scan"),
                    dbc.ModalBody([
                        dbc.Form([
                            dbc.Row([
                                dbc.Label("Min cosine", html_for="min-cosine", width=4),
                                dbc.Col(
                                    dbc.Input(id="min-cosine", type="number", placeholder="0.7", value=0.7, step=0.1),
                                    width=8),
                            ], className="mb-3"),
                            dbc.Row([
                                dbc.Label("Min matching peaks", html_for="min-matching-peaks", width=4),
                                dbc.Col(
                                    dbc.Input(id="min-matching-peaks", type="number", placeholder="6", value=6, step=1),
                                    width=8),
                            ], className="mb-3"),
                            dbc.Row([
                                dbc.Label("USI", html_for="usi", width=4),
                                dbc.Col(dbc.Input(id="usi", type="text", placeholder="mzspec:....",
                                                  value="mzspec:GNPS:GNPS-LIBRARY:accession:CCMSLIB00005435737",
                                                  style={'width': '100%'}),
                                        width=8),
                            ], className="mb-3"),
                            dbc.Row([
                                dbc.Label("Fragment Tolerance [mz]", html_for="fragment-tolerance", width=4),
                                dbc.Col(
                                    dbc.Input(id="fragment-tolerance", type="number", placeholder="0.02", value=0.02,
                                              step=0.01), width=8),
                            ], className="mb-3"),
                            dbc.Row([
                                dbc.Label("Precursor Tolerance [mz]", html_for="precursor-tolerance", width=4),
                                dbc.Col(
                                    dbc.Input(id="precursor-tolerance", type="number", placeholder="0.02", value=0.02,
                                              step=0.01), width=8),
                            ], className="mb-3"),
                        ])
                    ]),
                    dbc.ModalFooter(
                        dbc.Button("Submit", id="submit-fasstmasst", color="primary")
                    )
                ],
                id="fasstmasst-modal",
                is_open=False
            ),
        ], width=9)
    ], align="start")
])


# setting tracking token
dash_app.index_string = """<!DOCTYPE html>
<html>
    <head>
        <!-- Umami Analytics -->
        <script async defer data-website-id="74bc9983-13c4-4da0-89ae-b78209c13aaf" src="https://analytics.gnps2.org/umami.js"></script>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>"""


# Main app layout
dash_app.layout = html.Div([
    dcc.Location(id='url', refresh=False),
    navbar,
    panredu_layout
])





# Helper function for parsing filtering expressions
def split_filter_part(filter_part):

    print(filter_part, file=sys.stderr, flush=True)
    operators = [
        's>=',
        's<=',
        's>',
        's<',
        's!=',
        's=',
        '>=',
        '<=',
        '>',
        '<',
        '!=',
        '=',
        'contains',
        'scontains',
        'datestartswith',
    ]
    for operator in operators:
        regex = r'\{(?P<col_name>[^\}]+)\} ' + re.escape(operator) + r' "?(.+?)"?$'
        filter_part = filter_part.strip()
        match = re.match(regex, filter_part)
        if match:
            col_name = match.group('col_name')
            value = match.group(2)
            operator = operator.strip()

            print(col_name, operator, value, file=sys.stderr, flush=True)
            return col_name, operator, value
    return None, None, None



@dash_app.callback(
    Output("summary-stats", "children"),
    Input("data-table", "page_current")
)
def update_summary_stats(n_clicks):
    
    df_redu = _load_redu_sampledata()


    last_modified = _metadata_last_modified()


    last_modified = last_modified.strftime("%Y-%m-%d %H:%M %Z")


    total_files = len(df_redu)
    unique_datasets = df_redu['ATTRIBUTE_DatasetAccession'].nunique()


    data_source_counts = df_redu['DataSource'].value_counts().to_dict()


    unique_taxonomies = df_redu['NCBITaxonomy'].nunique() - 1  

    unique_divisions = [
        (division, taxonomies) for division, taxonomies in df_redu[df_redu['NCBIDivision'].notna()]
        .groupby('NCBIDivision')['NCBITaxonomy']
        .nunique().items() if taxonomies >= 10
    ]
    # Human and Mouse Data Specifics
    human_samples = len(df_redu[df_redu['NCBITaxonomy'] == '9606|Homo sapiens'])
    human_bodyparts = df_redu.loc[df_redu['NCBITaxonomy'] == '9606|Homo sapiens', 'UBERONBodyPartName'].nunique() - 1
    human_diseases = df_redu.loc[df_redu['NCBITaxonomy'] == '9606|Homo sapiens', 'DOIDCommonName'].nunique() - 1

    mouse_samples = len(df_redu[df_redu['NCBITaxonomy'].isin(['10088|Mus', '10090|Mus musculus'])])
    mouse_bodyparts = df_redu.loc[df_redu['NCBITaxonomy'].isin(
        ['10088|Mus', '10090|Mus musculus']), 'UBERONBodyPartName'].nunique() - 1
    mouse_diseases = df_redu.loc[df_redu['NCBITaxonomy'].isin(
        ['10088|Mus', '10090|Mus musculus']), 'DOIDCommonName'].nunique() - 1

    # Compose card children based on these values
    stats_card_content = [
        html.H5(f"Total Files: {total_files:,}"),
        html.H5(f"Unique Datasets: {unique_datasets}"),
        html.H5('Files by DataSource:'),
        html.Ul([html.Li(f"{key}: {value}") for key, value in data_source_counts.items()]),
        html.H5('Represented Taxonomies:'),
        html.P(f"Total Unique Taxonomies: {unique_taxonomies}:"),
        html.Ul([html.Li(f"{division}: {count}") for division, count in unique_divisions]),
        html.H5('Human/Mouse data:'),
        html.P(f"Homo Sapiens: {human_samples}"),
        html.Ul([
            html.Li(f"Unique Bodyparts: {human_bodyparts}"),
            html.Li(f"Unique Diseases: {human_diseases}")
        ]),
        html.P(f"Mus Musculus: {mouse_samples}"),
        html.Ul([
            html.Li(f"Unique Bodyparts: {mouse_bodyparts}"),
            html.Li(f"Unique Diseases: {mouse_diseases}")
        ]),
        html.Hr(),
        html.Div("Last Modified - {}".format(last_modified))
    ]

    return stats_card_content




@dash_app.callback(
    Output("data-table", "hidden_columns"),
    Output("data-table", "filter_query"),
    Input("subset-mzml-button", "n_clicks"),
    State("data-table", "filter_query"),
    State("data-table", "columns"),
    State("data-table", "hidden_columns"),
    Input('example-filter-human', 'n_clicks'),
    Input('example-filter-plant', 'n_clicks'),
    Input('example-filter-orbitrap', 'n_clicks'),
    Input('example-filter-complex', 'n_clicks'),
    Input('example-filter-multi', 'n_clicks'),
    Input('example-filter-lipids', 'n_clicks'),
    prevent_initial_call=True
)
def populate_filters(n_clicks_mzml, 
                     old_condition,
                     current_columns,
                     hidden_columns,
                     human_clicks,
                     plant_clicks,
                     orbitrap_clicks,
                     complex_clicks,
                     lipids_clicks,
                     multi_clicks):


    ctx = callback_context
    if not ctx.triggered:
        raise PreventUpdate

    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]


    if triggered_id == 'subset-mzml-button':
        new_condition = '{USI} contains ".(mzML|mzXML)$"'
        out_condition = f"{old_condition} && {new_condition}" if old_condition else new_condition

        if 'USI' in hidden_columns:
            hidden_columns.remove('USI')


    elif triggered_id == 'example-filter-human':
        out_condition = '{NCBITaxonomy} contains "Homo sapiens"'

        if 'NCBITaxonomy' in hidden_columns:
            hidden_columns.remove('NCBITaxonomy')        

    elif triggered_id == 'example-filter-plant':
        out_condition = '{SampleType} contains "plant"'

        if 'SampleType' in hidden_columns:
            hidden_columns.remove('SampleType')    

    elif triggered_id == 'example-filter-orbitrap':
        out_condition = '{MassSpectrometer} contains "(Orbitrap|Exactive|Exploris|Astral)"'

        if 'MassSpectrometer' in hidden_columns:
            hidden_columns.remove('MassSpectrometer')    

    elif triggered_id == 'example-filter-complex':
        out_condition = '{NCBITaxonomy} contains "(Homo|Mus)(?!.*musculus)"'
        
        if 'NCBITaxonomy' in hidden_columns:
            hidden_columns.remove('NCBITaxonomy')    

    elif triggered_id == 'example-filter-multi':
        out_condition = '{UBERONBodyPartName} contains "blood" && {NCBITaxonomy} contains "Rattus norvegicus"'

        if 'UBERONBodyPartName' in hidden_columns:
            hidden_columns.remove('UBERONBodyPartName')

        if 'NCBITaxonomy' in hidden_columns:
            hidden_columns.remove('NCBITaxonomy')

    elif triggered_id == 'example-filter-lipids':
        out_condition = '{ChromatographyAndPhase} contains "reverse phase" && {SampleExtractionMethod} contains "(butanol|dichloromethane|isopropanol|methyltertbutylether)" && {MS2spectra_count} > 0'

        if 'ChromatographyAndPhase' in hidden_columns:
            hidden_columns.remove('ChromatographyAndPhase')

        if 'SampleExtractionMethod' in hidden_columns:
            hidden_columns.remove('SampleExtractionMethod')

        if 'MS2spectra_count' in hidden_columns:
            hidden_columns.remove('MS2spectra_count')
        
    else:
        out_condition = old_condition



    return hidden_columns, out_condition



@dash_app.callback(
    Output("data-table", "data"),
    Output("rows-remaining", "children"),
    Output("page-count", "children"),
    Output("mn-button", "href"),
    Output("massql-button", "href"),
    Output("dashboard-button", "href"),
    Output("loading-output-232", "children"),
    Input("data-table", "page_current"),
    Input("data-table", "page_size"),
    Input("data-table", "sort_by"),
    Input("data-table", "filter_query"),
    Input('data-table', 'selected_rows'),
    Input("network-link-button", "n_clicks"),
    State("data-table", "columns")
)
def update_table_display(page_current, page_size, sort_by, filter_query, selected_rows, visible_columns, n_clicks):

    print('first filter state', file=sys.stderr, flush=True)
    print(filter_query, file=sys.stderr, flush=True)

    df_redu = _load_redu_sampledata()

    df_redu_filtered = _filter_redu_sampledata(df_redu, filter_query)

    # Sorting
    if sort_by:
        df_redu_filtered = df_redu_filtered.sort_values(
            [col['column_id'] for col in sort_by],
            ascending=[col['direction'] == 'asc' for col in sort_by],
            inplace=False
        )

    # Pagination
    total_filtered_rows = len(df_redu_filtered)
    total_pages = max(1, math.ceil(total_filtered_rows / page_size))
    page_info = f"Page {page_current + 1} of {total_pages}"
    rows_remaining_text = f"{total_filtered_rows} files remaining"

    # Slice data based on current page
    start_idx = page_current * page_size
    end_idx = start_idx + page_size
    paginated_data = df_redu_filtered.iloc[start_idx:end_idx]

    # Convert paginated data to dictionary format for DataTable
    paginated_data_dict = paginated_data.to_dict('records')


    networking_gnps2_url = "https://gnps2.org/workflowinput?workflowname=classical_networking_workflow"
    massql_gnps2_url = "https://gnps2.org/workflowinput?workflowname=massql_workflow"
    dashboard_gnps2_url = "https://dashboard.gnps2.org/"
    if selected_rows:
        params = "\n".join(paginated_data_dict[i]['USI'] for i in selected_rows)

        hash_params = {
            "usi": params,
        }

        massql_gnps2_url = massql_gnps2_url + "#" + json.dumps(hash_params)
        networking_gnps2_url = networking_gnps2_url + "#" + json.dumps(hash_params)

        dashboard_params = {
            "usi": params,
            "usi2": ""
        }

        dashboard_gnps2_url = dashboard_gnps2_url + "#" + json.dumps(dashboard_params)


    return  paginated_data_dict, \
            rows_remaining_text, \
            page_info, \
            networking_gnps2_url, \
            massql_gnps2_url, \
            dashboard_gnps2_url, \
            ""


@dash_app.callback(
    Output("download-dataframe-csv", "data"),
    Input("download-button", "n_clicks"),
    Input("USIdownload-button", "n_clicks"),
    State("data-table", "filter_query"),
    State("data-table", "columns"),
    prevent_initial_call=True
)
def download_filtered_data(n_clicks, n_clicks2, filter_query, visible_columns):
    if not n_clicks and not n_clicks2:
        raise PreventUpdate

    df_redu = _load_redu_sampledata()
    df_redu_filtered = _filter_redu_sampledata(df_redu, filter_query)

    ctx = callback_context

    if ctx.triggered[0]['prop_id'].split('.')[0] == 'USIdownload-button':

        df_redu_filtered = df_redu_filtered.rename(columns={'USI': 'usi'})

        df_redu_filtered = df_redu_filtered[['usi']]
        return dcc.send_data_frame(df_redu_filtered.to_csv, "usis.csv", index=False)

    return dcc.send_data_frame(df_redu_filtered.to_csv, "filtered_dataset.csv", index=False)


if __name__ == '__main__':
    app.run_server(debug=True)