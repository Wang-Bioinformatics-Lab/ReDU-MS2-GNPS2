import requests
import os
import dash
from dash import dcc, html, dash_table, Input, Output, State, callback_context, Dash
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
import pandas as pd
import re
import math
import clipboard
import time

from app import app

PATH_TO_SAMPLE_INFORMATION = '/app/workflows/PublicDataset_ReDU_Metadata_Workflow/nf_output/all_sampleinformation.tsv'

# Load the data
df_redu = pd.read_csv(PATH_TO_SAMPLE_INFORMATION, sep='\t')

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
server = app.server  # Expose the server variable

# Determine which columns are hidden by default
hidden_columns = [col for col in all_columns_ordered if col not in default_columns]


# Make logo path
image_url = app.get_asset_url("ReDU_logo_with_url.PNG")


# Create the navigation menu with the logo
navbar = dbc.Navbar(
    dbc.Container([
        html.A(
            html.Img(src=app.get_asset_url("ReDU_logo_with_url.png"), height="80px", style={"padding-right": "15px"}),
            href="/",
            style={"textDecoration": "none"}
        ),
        dbc.NavbarSimple(
            children=[
                dbc.NavItem(dbc.NavLink("Home", href="/", active="exact", style={"fontSize": "20px", "margin-right": "100px"})),
                dbc.NavItem(dbc.NavLink("Contribute Your Data", href="https://docs.google.com/spreadsheets/d/10U0xnJUKa_mD0H_9suH1KJAlJD9io9e4chBX8EAHneE/edit?gid=1001603307#gid=1001603307", target="_blank", external_link=True, active="exact", style={"fontSize": "20px", "margin-right": "100px"})),
                dbc.NavItem(dbc.NavLink("ReDU Dashboard - Documentation", href="/documentation", active="exact", style={"fontSize": "20px", "margin-right": "100px"})),
                dbc.NavItem(dbc.NavLink("Download ReDU", href="/download-tsv", id="download-complete-link", style={"fontSize": "20px", "margin-right": "20px"})),
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
                dbc.CardBody([
                    html.H5(f"Total Files: {len(df_redu):,}"),
                    html.H5(f"Unique Datasets: {df_redu['ATTRIBUTE_DatasetAccession'].nunique()}"),
                    html.H5('Files by DataSource:'),
                    html.Ul([html.Li(f"{key}: {value}") for key, value in
                             df_redu['DataSource'].value_counts().to_dict().items()]),
                    html.H5('Represented Taxonomies:'),
                    html.P(f"Total Unique Taxonomies: {df_redu['NCBITaxonomy'].nunique() - 1}"),
                    html.Ul([
                        html.Li(f"{division}: {taxonomies}")
                        for division, taxonomies in df_redu[df_redu['NCBIDivision'].notna()]
                        .groupby('NCBIDivision')['NCBITaxonomy']
                        .nunique()
                        .items()
                        if taxonomies >= 10
                    ]),
                    html.H5('Human/Mouse data:'),
                    html.P(f"Homo Sapiens: {len(df_redu[df_redu['NCBITaxonomy'] == '9606|Homo sapiens'])}"),
                    html.Ul([
                        html.Li(
                            f"Unique Bodyparts: {df_redu.loc[df_redu['NCBITaxonomy'] == '9606|Homo sapiens', 'UBERONBodyPartName'].nunique() - 1}"),
                        html.Li(
                            f"Unique Diseases: {df_redu.loc[df_redu['NCBITaxonomy'] == '9606|Homo sapiens', 'DOIDCommonName'].nunique() - 1}")
                    ]),
                    html.P(f"Mus Musculus: {len(df_redu[df_redu['NCBITaxonomy'].isin(['10088|Mus', '10090|Mus musculus'])])}"),
                    html.Ul([
                        html.Li(
                            f"Unique Bodyparts: {df_redu.loc[df_redu['NCBITaxonomy'].isin(['10088|Mus', '10090|Mus musculus']), 'UBERONBodyPartName'].nunique() - 1}"),
                        html.Li(
                            f"Unique Diseases: {df_redu.loc[df_redu['NCBITaxonomy'].isin(['10088|Mus', '10090|Mus musculus']), 'DOIDCommonName'].nunique() - 1}")
                    ]),
                ]),
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
                        html.A('MetaboLights', href='https://www.ebi.ac.uk/metabolights/', target='_blank', style={'fontSize': '18px'}),
                        ', ',
                        html.A('Metabolomics Workbench', href='https://www.metabolomicsworkbench.org/', target='_blank', style={'fontSize': '18px'}),
                        ', and ',
                        html.A('GNPS', href='https://gnps.ucsd.edu/ProteoSAFe/datasets.jsp#%7B%22query%22%3A%7B%7D%2C%22table_sort_history%22%3A%22createdMillis_dsc%22%2C%22title_input%22%3A%22GNPS%22', target='_blank', style={'fontSize': '18px'}),
                        '.',
                        html.Br(), html.Br(),
                        'Please ',
                        html.A('contribute your data', href='https://docs.google.com/spreadsheets/d/10U0xnJUKa_mD0H_9suH1KJAlJD9io9e4chBX8EAHneE/edit?usp=sharing', target='_blank', style={'fontSize': '18px'}),
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

                    dbc.Col(dbc.Button("Subset Table to Files Matching MS2", id="open-fasstmasst-button", color="info",
                                       className="mb-4"),
                            width="auto"),
                    dbc.Col(dbc.Button("Subset Table to mz(X)ML files", id="subset-mzml-button", color="info",
                                       className="mb-4"),
                            width="auto"),
                    dbc.Col(dbc.Button("Reset All Filters", id="reset-filters-button", color="warning", className="mb-4"),
                            width="auto"),
                    dbc.Col(dbc.Button("Download Filtered Table", id="download-button", color="primary",
                                       className="mb-2"), width="auto")
                ],
                className="mb-1 mt-3 d-flex justify-content-start"
            ),

            # New Button Row
            dbc.Row(
                [
                    dbc.Col(dbc.Button("Copy Filtered USIs for Analysis", id="copy-button", color="secondary", className="mb-2"),
                            width="auto"),

                    dbc.Col(dbc.Button("USIs --> Molecular Networking", id="MN-button", color="primary",
                                       className="mb-2", href="https://gnps2.org/workflowinput?workflowname=classical_networking_workflow",
                                       target="_blank"),
                            width="auto"),

                    dbc.Col(dbc.Button("USIs --> MassQL", id="massql-button", color="primary",
                                       className="mb-4", href="https://gnps2.org/workflowinput?workflowname=massql_workflow",
                                       target="_blank"),
                            width="auto"),

                    dbc.Col(dbc.Button("USIs --> Raw Data Download", id="USIdownload-button", color="primary",
                                       className="mb-2", href="https://github.com/Wang-Bioinformatics-Lab/downloadpublicdata",
                                       target="_blank"),
                            width="auto")
                ],
                className="mb-2 mt-1 d-flex justify-content-start"
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
                #page_action='custom',
                filter_action='custom',
                #filter_action='native',
                #filter_query='{USI} contains ".(mzML|mzXML)$"',
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
            dcc.Clipboard(id="clipboard", content='', style={'display': 'none'}),
            dcc.Store(id="clipboard-content-store"),
            dcc.Store(id='update-happened', storage_type='memory'),

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
                                                  value="mzspec:GNPS:GNPS-LIBRARY:accession:CCMSLIB00005435737", style={'width': '100%'}),
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


# Layout for the Documentation page
documentation_layout = dbc.Container(fluid=True, children=[
    html.H2("ReDU Dashboard - Documentation", className='text-center my-4'),
    html.Div([
        dcc.Markdown('''
**Welcome to the Dataset Investigation Dashboard!**


Happy exploring!
        ''')
    ], className='mb-4')

    ])

# Main app layout
app.layout = html.Div([
    dcc.Location(id='url', refresh=False),
    navbar,
    html.Div(id='page-content')
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

# Callback to update data-table.filter_query and display current filters
@dash_app.callback(
    Output('data-table', 'filter_query'),
    Input('reset-filters-button', 'n_clicks'),
    Input('example-filter-human', 'n_clicks'),
    Input('example-filter-plant', 'n_clicks'),
    Input('example-filter-orbitrap', 'n_clicks'),
    Input('example-filter-complex', 'n_clicks'),
    Input('example-filter-multi', 'n_clicks'),
    prevent_initial_call=True,
)
def update_data_table_filter_query(reset_clicks, human_clicks, plant_clicks, orbitrap_clicks, complex_clicks, multi_clicks):
    ctx = callback_context
    if not ctx.triggered:
        raise PreventUpdate

    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]


    # If Reset Filters is clicked
    if triggered_id == 'reset-filters-button':
        # Clear the filter query
        return ''

    # Logic for example filters follows...
    if triggered_id == 'example-filter-human':
        new_condition = '{NCBITaxonomy} contains "Homo sapiens"'
    elif triggered_id == 'example-filter-plant':
        new_condition = '{SampleType} contains "Plant"'
    elif triggered_id == 'example-filter-orbitrap':
        new_condition = '{MassSpectrometer} contains "(Orbitrap|Exactive|Exploris|Astral)"'
    elif triggered_id == 'example-filter-complex':
        new_condition = '{NCBITaxonomy} contains "(Homo|Mus)(?!.*musculus)"'
    elif triggered_id == 'example-filter-multi':
        new_condition = '{UBERONBodyPartName} contains "blood" && {NCBITaxonomy} contains "Rattus norvegicus"'
    else:
        raise PreventUpdate

    print(f"Applying new filter: {new_condition}")
    return new_condition

@dash_app.callback(
    Output("update-happened", "data"),
    Output("data-table", "page_current"),
    Input("url", "pathname"),
    Input("data-table", "filter_query"),
    Input('reset-filters-button', 'n_clicks'),
    Input("submit-fasstmasst", "n_clicks"),
    Input('subset-mzml-button', 'n_clicks'),
    State("usi", "value"),
    State("min-cosine", "value"),
    State("min-matching-peaks", "value"),
    State("fragment-tolerance", "value"),
    State("precursor-tolerance", "value"),
    prevent_initial_call=False
)
def update_filtered_data_store(pathname, filter_query, reset_button, submit_n_clicks, mzml_button, usi, min_cos, min_fragments,
                               fragment_mz_tol, precursor_mz_tol):

    ctx = callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]

    df_redu_filtered = pd.read_csv(PATH_TO_SAMPLE_INFORMATION, sep='\t')

    # TODO: We can't do these things because we don't maintain state
    # Initialize dff with full dataset for fallback
    # if triggered_id == 'reset-filters-button':
    #     df_redu_filtered = df_redu.copy()
    # else:
    #     df_redu_filtered = df_redu_filtered

    # if triggered_id == "subset-mzml-button":
    #     df_redu_filtered = df_redu_filtered[df_redu_filtered['USI'].astype(str).str.contains('.(mzML|mzXML)$', case=True, na=False, regex=True)]


    #Filter via data-table filter_query
    if triggered_id == "data-table" and filter_query:
        filtering_expressions = filter_query.split(' && ')
        for filter_part in filtering_expressions:
            col_name, operator, value = split_filter_part(filter_part)
            if operator and col_name in df_redu_filtered.columns:
                # Apply the operator logic

                if value == "":  # Check for empty string to clear filter
                    continue  # Skip this filter, effectively removing it

                if operator == 'contains':
                    df_redu_filtered = df_redu_filtered[df_redu_filtered[col_name].astype(str).str.contains(value, case=False, na=False, regex=True)]
                elif operator == 'scontains':
                    df_redu_filtered = df_redu_filtered[df_redu_filtered[col_name].astype(str).str.contains(value, case=True, na=False, regex=True)]
                elif operator == '=':
                    df_redu_filtered = df_redu_filtered[df_redu_filtered[col_name] == value]
                elif operator == '!=':
                    df_redu_filtered = df_redu_filtered[df_redu_filtered[col_name] != value]
                elif operator == '<':
                    df_redu_filtered = df_redu_filtered[pd.to_numeric(df_redu_filtered[col_name], errors='coerce') < float(value)]
                elif operator == '<=':
                    df_redu_filtered = df_redu_filtered[pd.to_numeric(df_redu_filtered[col_name], errors='coerce') <= float(value)]
                elif operator == '>':
                    df_redu_filtered = df_redu_filtered[pd.to_numeric(df_redu_filtered[col_name], errors='coerce') > float(value)]
                elif operator == '>=':
                    df_redu_filtered = df_redu_filtered[pd.to_numeric(df_redu_filtered[col_name], errors='coerce') >= float(value)]
                elif operator == 'in':
                    values = [v.strip() for v in value.split(',')]
                    df_redu_filtered = df_redu_filtered[df_redu_filtered[col_name].isin(values)]
                elif operator == 'nin':
                    values = [v.strip() for v in value.split(',')]
                    df_redu_filtered = df_redu_filtered[~df_redu_filtered[col_name].isin(values)]
            print(f"Filtered {col_name} with {operator} {value}. Rows remaining: {len(df_redu_filtered)}")

    # Filter via submit-fasstmasst
    elif triggered_id == "submit-fasstmasst":
        try:
            params = {
                "usi": usi,
                "library": 'metabolomicspanrepo_index_latest',
                "analog": "No",
                "pm_tolerance": precursor_mz_tol,
                "fragment_tolerance": fragment_mz_tol,
                "cosine_threshold": min_cos,
                "cache": "Yes"
            }
            r = requests.get("https://fasst.gnps2.org/search", params=params, timeout=50)
            r.raise_for_status()

            response_list = r.json().get('results', [])
            if response_list:
                df_response = pd.DataFrame(response_list)
                df_response = df_response[df_response['Matching Peaks'] >= min_fragments]
                if not df_response.empty:
                    df_response['USI'] = df_response['USI'].apply(lambda x: ":".join(x.split(":")[:-2]))
                    matching_usis = df_response['USI'].unique()
                    df_redu_filtered = df_redu_filtered[df_redu_filtered['USI'].isin(matching_usis)]
                    print("Filtered rows after USI subset:", len(df_redu_filtered))  # Debug

        except Exception as e:
            print(f"Error during API request: {e}")
            return []

    # Return the fully filtered dataset for storage
    return {"timestamp": time.time()}, 0



# Continue with other callbacks
@dash_app.callback(
    Output("data-table", "data"),
    Output("rows-remaining", "children"),
    Output("page-count", "children"),
    Input("update-happened", "data"),
    Input("data-table", "page_current"),
    Input("data-table", "page_size"),
    Input("data-table", "sort_by"),
    prevent_initial_call=True
)
def update_table_display(update_check, page_current, page_size, sort_by):
    global df_redu_filtered

    ctx = callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if triggered_id == 'update-happened':
        page_current = 0

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

    paginated_data_dict = paginated_data.to_dict('records')

    return paginated_data_dict, rows_remaining_text, page_info




@dash_app.callback(
    Output("clipboard-content-store", "data"),
    Input("copy-button", "n_clicks"),
    prevent_initial_call=True,
)
def update_clipboard_content(n_clicks):

    if n_clicks is None:
        raise PreventUpdate

    global df_redu_filtered
    if n_clicks:
        usis = df_redu_filtered['USI'].dropna().tolist()
        usi_text = '\n'.join(usis)
        clipboard.copy(usi_text)
        return usi_text
    return ''


@dash_app.callback(
    Output("download-dataframe-csv", "data"),
    Input("download-button", "n_clicks"),
    prevent_initial_call=True,
)
def download_filtered_data(n_clicks):
    global df_redu_filtered
    if n_clicks is None:
        raise PreventUpdate

    return dcc.send_data_frame(df_redu_filtered.to_csv, "filtered_dataset.csv", index=False)


# Callbacks for opening and closing the modal
@dash_app.callback(
    Output("fasstmasst-modal", "is_open"),
    [Input("open-fasstmasst-button", "n_clicks"), Input("submit-fasstmasst", "n_clicks")],
    [State("fasstmasst-modal", "is_open")],
)
def toggle_modal(open_click, submit_click, is_open):
    if open_click or submit_click:
        return not is_open
    return is_open


# Callback to render the appropriate page
@dash_app.callback(Output('page-content', 'children'),
              [Input('url', 'pathname')])
def display_page(pathname):
    if pathname == '/documentation':
        return documentation_layout
    else:
        return panredu_layout


@dash_app.callback(
    Output("download-complete-tsv", "data"),
    Input("download-complete-link", "n_clicks"),
    prevent_initial_call=True
)
def download_df(n_clicks):
    global df_redu
    return dcc.send_data_frame(df_redu.to_csv, "redu_complete.tsv", sep="\t", index=False)

if __name__ == '__main__':
    app.run_server(debug=True)