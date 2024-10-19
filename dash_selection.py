import requests
import os
import dash
from dash import dcc, html, dash_table, Input, Output, State, callback_context, Dash
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
import pandas as pd
import re
import math
import json

from app import app

from utils import _load_redu_sampledata, _metadata_last_modified

def _filter_redu_sampledata(redu_df, filter_query=None):

    if filter_query:
        filtering_expressions = filter_query.split(' && ')
        for filter_part in filtering_expressions:
            col_name, operator, value = split_filter_part(filter_part)
            if operator and col_name in redu_df.columns:
                # Apply operator logic as previously defined
                if operator == 'contains':
                    redu_df = redu_df[
                        redu_df[col_name].astype(str).str.contains(value, case=False, na=False, regex=True)]
                if operator == 'scontains':
                    redu_df = redu_df[
                        redu_df[col_name].astype(str).str.contains(value, case=True, na=False, regex=True)]
                elif operator == '=':
                    redu_df = redu_df[redu_df[col_name] == value]
                elif operator == '!=':
                    redu_df = redu_df[redu_df[col_name] != value]
                elif operator == '<':
                    redu_df = redu_df[
                        pd.to_numeric(redu_df[col_name], errors='coerce') < float(value)]
                elif operator == '<=':
                    redu_df = redu_df[
                        pd.to_numeric(redu_df[col_name], errors='coerce') <= float(value)]
                elif operator == '>':
                    redu_df = redu_df[
                        pd.to_numeric(redu_df[col_name], errors='coerce') > float(value)]
                elif operator == '>=':
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
image_url = dash_app.get_asset_url("ReDU_logo_with_url.PNG")


# Create the navigation menu with the logo
navbar = dbc.Navbar(
    dbc.Container([
        html.A(
            html.Img(src=dash_app.get_asset_url("ReDU_logo_with_url.png"), height="80px", style={"padding-right": "15px"}),
            href="/",
            style={"textDecoration": "none"}
        ),
        dbc.NavbarSimple(
            children=[
                dbc.NavItem(
                    html.A(
                        "Contribute Your Data",
                        href="https://docs.google.com/spreadsheets/d/10U0xnJUKa_mD0H_9suH1KJAlJD9io9e4chBX8EAHneE/edit?gid=1001603307#gid=1001603307",
                        target="_blank",
                        className="nav-link",
                        style={"fontSize": "20px", "margin-right": "100px"}
                    )
                ),
                dbc.NavItem(
                    html.A(
                        "ReDU Dashboard - Documentation",
                        href="https://mwang87.github.io/ReDU-MS2-Documentation/",
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
                               href='https://docs.google.com/spreadsheets/d/10U0xnJUKa_mD0H_9suH1KJAlJD9io9e4chBX8EAHneE/edit?usp=sharing',
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
                            html.H3(['Filter Table'], style={'font-weight': 'bold', 'text-decoration': 'underline', 'text-align': 'center', 'width': '100%', 'margin': '0 auto'}),
                            dbc.Button("Subset Table to mz(X)ML files", id="subset-mzml-button", color="info",
                                       className="mb-2", style={"width": "100%", "height": "22%", "text-align": "center"}),
                            html.P(['Or use the column filters below,..'],
                                   className='text-center mb-4', style={'fontSize': '18px'})
                            # dbc.Button("Reset All Filters", id="reset-filters-button", color="info",
                            #            className="mb-2", style={"width": "100%", "height": "22%", "text-align": "center"})
                        ],
                        width=3, className="d-flex flex-column align-items-start justify-content-start",
                        style={"height": "200px"}
                    ),
                    dbc.Col(
                        [
                            html.H3(['Download selection'], style={'font-weight': 'bold', 'text-decoration': 'underline', 'text-align': 'center', 'width': '100%', 'margin': '0 auto'}),
                            dbc.Button("Download Filtered Table", id="download-button", color="warning",
                                       className="mb-2", style={"width": "100%", "height": "22%", "text-align": "center"})#,
                            # dbc.Button("Copy Filtered USIs for Analysis", id="copy-button", color="warning",
                            #            className="mb-2", style={"width": "100%", "height": "22%", "text-align": "center"})
                        ],
                        width=3, className="d-flex flex-column align-items-start justify-content-start",
                        style={"height": "200px"}
                    ),
                    dbc.Col(
                        [
                            html.H3(['Downstream tooling'], style={'font-weight': 'bold', 'text-decoration': 'underline', 'text-align': 'center', 'width': '100%', 'margin': '0 auto'}),
                            dbc.Button("USIs --> Molecular Networking", id="mn-button", color="primary",
                                       className="mb-2", style={"width": "100%", "height": "100%", "text-align": "center"},
                                       href="https://gnps2.org/workflowinput?workflowname=classical_networking_workflow",
                                       target="_blank"),
                            dbc.Button("USIs --> MassQL", id="massql-button", color="primary",
                                       className="mb-2", style={"width": "100%", "height": "100%", "text-align": "center"},
                                       href="https://gnps2.org/workflowinput?workflowname=massql_workflow",
                                       target="_blank"),
                            dbc.Button("USIs --> Raw Data Download", id="USIdownload-button", color="primary",
                                       className="mb-2", style={"width": "100%", "height": "100%", "text-align": "center"},
                                       href="https://github.com/Wang-Bioinformatics-Lab/downloadpublicdata",
                                       target="_blank")
                        ],
                        width=3, className="d-flex flex-column align-items-start justify-content-around",
                        style={"height": "200px"}
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
                # page_action='custom',
                filter_action='custom',
                # filter_action='native',
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
    operators = [
        '>=',
        '<=',
        '>',
        '<',
        '!=',
        '=',
        'contains',
        'scontains',
        'datestartswith',
        'sw',
        'ew',
        'in',
        'nin',
    ]
    for operator in operators:
        regex = r'\{(?P<col_name>[^\}]+)\} ' + re.escape(operator) + r' "?(.+?)"?$'
        filter_part = filter_part.strip()
        match = re.match(regex, filter_part)
        if match:
            col_name = match.group('col_name')
            value = match.group(2)
            operator = operator.strip()
            return col_name, operator, value
    return None, None, None



@dash_app.callback(
    Output("summary-stats", "children"),
    Input("data-table", "page_current")
)
def update_summary_stats(n_clicks):
    # Load the full dataset
    df_redu = _load_redu_sampledata()

    # Getting the last modified date of the file
    last_modified = _metadata_last_modified()

    # convert to string without the seconds but with timezone
    last_modified = last_modified.strftime("%Y-%m-%d %H:%M %Z")

    # Calculate statistics
    total_files = len(df_redu)
    unique_datasets = df_redu['ATTRIBUTE_DatasetAccession'].nunique()

    # Files by DataSource
    data_source_counts = df_redu['DataSource'].value_counts().to_dict()

    # Represented Taxonomies
    unique_taxonomies = df_redu['NCBITaxonomy'].nunique() - 1  # Adjusted based on your original static values

    # NCBI Divisions
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
    Output("data-table", "columns"),
    Output("data-table", "filter_query"),
    Input("subset-mzml-button", "n_clicks"),
    Input("reset-filters-button", "n_clicks"),
    State("data-table", "filter_query"),
    State("data-table", "columns"),
    State("data-table", "hidden_columns"),
    Input('example-filter-human', 'n_clicks'),
    Input('example-filter-plant', 'n_clicks'),
    Input('example-filter-orbitrap', 'n_clicks'),
    Input('example-filter-complex', 'n_clicks'),
    Input('example-filter-multi', 'n_clicks'),
    prevent_initial_call=True
)
def populate_filters(n_clicks_mzml, 
                     n_clicks_reset,
                     old_condition,
                     current_columns,
                     hidden_columns,
                     human_clicks,
                     plant_clicks,
                     orbitrap_clicks,
                     complex_clicks,
                     multi_clicks):


    ctx = callback_context
    if not ctx.triggered:
        raise PreventUpdate

    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]

    # Ensure the USI column is visible
    columns_to_show = [col for col in current_columns if col['id'] not in hidden_columns]

    if triggered_id == 'subset-mzml-button':
        new_condition = '{USI} contains ".(mzML|mzXML)$"'
        out_condition = f"{old_condition} && {new_condition}" if old_condition else new_condition

    elif triggered_id == 'example-filter-human':
        out_condition = '{NCBITaxonomy} contains "Homo sapiens"'

    elif triggered_id == 'example-filter-plant':
        out_condition = '{SampleType} contains "Plant"'

    elif triggered_id == 'example-filter-orbitrap':
        out_condition = '{MassSpectrometer} contains "(Orbitrap|Exactive|Exploris|Astral)"'

    elif triggered_id == 'example-filter-complex':
        out_condition = '{NCBITaxonomy} contains "(Homo|Mus)(?!.*musculus)"'

    elif triggered_id == 'example-filter-multi':
        out_condition = '{UBERONBodyPartName} contains "blood" && {NCBITaxonomy} contains "Rattus norvegicus"'
    
    elif triggered_id == 'reset-filters-button':
        out_condition = ''

    else:
        out_condition = old_condition

    print(f"we are trying to update the text box with {out_condition}")

    return columns_to_show, out_condition



# Continue with other callbacks
@dash_app.callback(
    Output("data-table", "data"),
    Output("rows-remaining", "children"),
    Output("page-count", "children"),
    Output("mn-button", "href"),
    Output("massql-button", "href"),
    Input("data-table", "page_current"),
    Input("data-table", "page_size"),
    Input("data-table", "sort_by"),
    Input("data-table", "filter_query"),
    State("data-table", "columns")
)
def update_table_display(page_current, page_size, sort_by, filter_query, visible_columns):
    # Reload the base dataset from disk
    df_redu = _load_redu_sampledata()

    # Apply filters
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

    # Here we will take the first 50 records for linkouts for GNPS2 Analysis
    gnps_linkout_data_df = df_redu_filtered.head(50)
    # getting the USIs
    linkout_usis = gnps_linkout_data_df['USI'].tolist()

    # GNPS2 Networking URL 
    networking_gnps2_url = "https://gnps2.org/workflowinput?workflowname=classical_networking_workflow"
    hash_params = {
        "usi": "\n".join(linkout_usis),
    }

    networking_gnps2_url = networking_gnps2_url + "#" + json.dumps(hash_params)

    # massql href
    massql_gnps2_url = "https://gnps2.org/workflowinput?workflowname=massql_workflow"
    massql_gnps2_url = massql_gnps2_url + "#" + json.dumps(hash_params)



    return  paginated_data_dict, \
            rows_remaining_text, \
            page_info, \
            networking_gnps2_url, \
            massql_gnps2_url


@dash_app.callback(
    Output("download-dataframe-csv", "data"),
    Input("download-button", "n_clicks"),
    State("data-table", "filter_query"),
    State("data-table", "columns"),
    prevent_initial_call=True
)
def download_filtered_data(n_clicks, filter_query, visible_columns):
    if n_clicks is None:
        raise PreventUpdate

    # Reload and filter data on-demand
    df_redu = _load_redu_sampledata()
    df_redu_filtered = _filter_redu_sampledata(df_redu, filter_query)

    return dcc.send_data_frame(df_redu_filtered.to_csv, "filtered_dataset.csv", index=False)


# # Callbacks for opening and closing the modal
# @dash_app.callback(
#     Output("fasstmasst-modal", "is_open"),
#     [Input("open-fasstmasst-button", "n_clicks"), Input("submit-fasstmasst", "n_clicks")],
#     [State("fasstmasst-modal", "is_open")],
# )
# def toggle_modal(open_click, submit_click, is_open):
#     if open_click or submit_click:
#         return not is_open
#     return is_open



if __name__ == '__main__':
    app.run_server(debug=True)