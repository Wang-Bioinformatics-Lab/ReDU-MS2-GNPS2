import requests
import os
import dash
from dash import dcc, html, dash_table, Input, Output, State, callback_context, Dash
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
import pandas as pd
import re
import math

# Load the data
df = pd.read_csv('C:/Users/elabi/Downloads/all_sampleinformation.tsv', sep='\t')


# Define column configurations
default_columns = ["SampleType", "SampleTypeSub1", "NCBITaxonomy", "UBERONBodyPartName", "MassSpectrometer", "USI"]

# All columns in desired order
all_columns_ordered = default_columns + [col for col in df.columns if col not in default_columns]

# Initialize the Dash app with Bootstrap theme
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
app.config.suppress_callback_exceptions = True  # Allow callbacks for components not in the initial layout
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
                    html.H5(f"Total Files: {len(df):,}"),
                    html.H5(f"Unique Datasets: {df['ATTRIBUTE_DatasetAccession'].nunique()}"),
                    html.H5('Files by DataSource:'),
                    html.Ul([html.Li(f"{key}: {value}") for key, value in
                             df['DataSource'].value_counts().to_dict().items()]),
                    html.H5('Represented Taxonomies:'),
                    html.P(f"Total Unique Taxonomies: {df['NCBITaxonomy'].nunique() - 1}"),
                    html.Ul([
                        html.Li(f"{division}: {taxonomies}")
                        for division, taxonomies in df[df['NCBIDivision'].notna()]
                        .groupby('NCBIDivision')['NCBITaxonomy']
                        .nunique()
                        .items()
                        if taxonomies >= 10
                    ]),
                    html.H5('Human/Mouse data:'),
                    html.P(f"Homo Sapiens: {len(df[df['NCBITaxonomy'] == '9606|Homo sapiens'])}"),
                    html.Ul([
                        html.Li(
                            f"Unique Bodyparts: {df.loc[df['NCBITaxonomy'] == '9606|Homo sapiens', 'UBERONBodyPartName'].nunique() - 1}"),
                        html.Li(
                            f"Unique Diseases: {df.loc[df['NCBITaxonomy'] == '9606|Homo sapiens', 'DOIDCommonName'].nunique() - 1}")
                    ]),
                    html.P(f"Mus Musculus: {len(df[df['NCBITaxonomy'].isin(['10088|Mus', '10090|Mus musculus'])])}"),
                    html.Ul([
                        html.Li(
                            f"Unique Bodyparts: {df.loc[df['NCBITaxonomy'].isin(['10088|Mus', '10090|Mus musculus']), 'UBERONBodyPartName'].nunique() - 1}"),
                        html.Li(
                            f"Unique Diseases: {df.loc[df['NCBITaxonomy'].isin(['10088|Mus', '10090|Mus musculus']), 'DOIDCommonName'].nunique() - 1}")
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
                filter_action='custom',
                filter_query='{USI} contains ".(mzML|mzXML)$"',
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
            html.Div(id='rows-remaining', className='mt-2'),
            html.Div(id='page-count', className='mt-2'),
            html.Div(id='dummy-div', style={'display': 'none'}),


            # Additional Components if Needed
            dcc.Download(id="download-dataframe-csv"),
            dcc.Clipboard(id="clipboard", content='', style={'display': 'none'}),
            dcc.Store(id="clipboard-content-store"),
            dcc.Store(id='filtered-data-store', storage_type='memory'),

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

Use this dashboard to explore and filter datasets based on various attributes. Here's how you can interact with the dashboard:

---

### **Filtering Data**

You can filter the dataset using the text boxes at the top of each column in the data table. Below are the available operators and how to use them:

#### **Available Operators**

- **`=` or `eq`**: Equals
- **`!=` or `ne`**: Not equal to
- **`<` or `lt`**: Less than
- **`<=` or `le`**: Less than or equal to
- **`>` or `gt`**: Greater than
- **`>=` or `ge`**: Greater than or equal to
- **`contains`**: Contains the specified substring (case-insensitive)
- **`scontains`**: Contains the specified substring (case-sensitive)
- **`sw`**: String starts with the specified substring
- **`ew`**: String ends with the specified substring
- **`in`**: Value is in the list of specified values
- **`nin`**: Value is not in the list of specified values
- **`datestartswith`**: Date starts with the specified string (useful for date columns)

#### **How to Use Filters**

- **Basic Syntax**: `Operator "Value"`
  - **Example**: To filter for samples containing "Homo sapiens" in the `NCBITaxonomy` column, enter:
    ```
    contains "Homo sapiens"
    ```

- **Multiple Conditions**: You can combine multiple conditions using `&&` for logical AND.
  - **Example**: To filter for human blood samples, you can enter in the `NCBITaxonomy` column:
    ```
    contains "Homo sapiens"
    ```
    and in the `UBERONBodyPartName` column:
    ```
    contains "blood"
    ```

#### **Operator Examples**

1. **Equality and Inequality**

   - **Equals** (`=` or `eq`):
     ```
     = "Plant"
     ```
     Filters rows where the column value is exactly "Plant".

   - **Not Equal** (`!=` or `ne`):
     ```
     != "Plant"
     ```
     Excludes rows where the column value is "Plant".

2. **Numeric Comparisons**

   - **Greater Than** (`>` or `gt`):
     ```
     > 100
     ```
     Filters rows where the column value is greater than 100.

   - **Less Than or Equal To** (`<=` or `le`):
     ```
     <= 50
     ```
     Filters rows where the column value is less than or equal to 50.

3. **String Matching**

   - **Contains** (`contains`):
     ```
     contains "Orbitrap"
     ```
     Filters rows where the column value contains "Orbitrap" (case-insensitive).

   - **Case-Sensitive Contains** (`scontains`):
     ```
     scontains "Blood"
     ```
     Filters rows where the column value contains "Blood" with exact casing.

   - **Starts With** (`sw`):
     ```
     sw "Rat"
     ```
     Filters rows where the column value starts with "Rat".

   - **Ends With** (`ew`):
     ```
     ew "sample"
     ```
     Filters rows where the column value ends with "sample".

4. **List Membership**

   - **In List** (`in`):
     ```
     in "Blood, Plasma, Serum"
     ```
     Filters rows where the column value is "Blood", "Plasma", or "Serum".

   - **Not In List** (`nin`):
     ```
     nin "Urine, Saliva"
     ```
     Excludes rows where the column value is "Urine" or "Saliva".

5. **Regular Expressions**

   - **Complex Patterns**:
     ```
     contains "(Orbitrap|Exactive|Exploris|Astral)"
     ```
     Filters rows where the column value matches any of the specified terms. Use parentheses `()` for grouping and the pipe `|` as an OR operator in regex.

---

### **Interacting with the Dashboard**

- **Apply Filters**:

  - **Per-Column Filters**: Use the text boxes at the top of each column to apply filters specific to that column.
  - **Example Filters**: Click on the example links provided to quickly apply common filters. Note that applying an example filter will reset any existing filters.

- **Reset Filters**:

  - Click **"Reset Filters"** to clear all applied filters and start a new search.

- **Download and Copy**:

  - **Download Filtered Dataset**: Click this button to download the currently filtered dataset as a CSV file.
  - **Copy USIs to Clipboard**: Click this button to copy the USIs from the filtered dataset to your clipboard.

---

### **Examples**

1. **Filter for Human Samples**

   - In the `NCBITaxonomy` column filter box, enter:
     ```
     contains "Homo sapiens"
     ```

2. **Filter for Plant Samples**

   - In the `SampleType` column filter box, enter:
     ```
     contains "Plant"
     ```

3. **Filter for Specific Mass Spectrometers**

   - In the `MassSpectrometer` column filter box, enter:
     ```
     contains "(Orbitrap|Exactive|Exploris|Astral)"
     ```
     This uses a regex pattern to match any of the specified mass spectrometers.

4. **Filter for Complex Conditions**

   - To filter for entries in `NCBITaxonomy` that are either "Homo" or "Mus" but not "musculus", enter:
     ```
     contains "(Homo|Mus)(?!.*musculus)"
     ```
     This uses a negative lookahead in regex to exclude "musculus".

5. **Filter for Blood Samples from Rattus norvegicus**

   - In the `UBERONBodyPartName` column filter box, enter:
     ```
     contains "blood"
     ```
   - In the `NCBITaxonomy` column filter box, enter:
     ```
     contains "Rattus norvegicus"
     ```

---

### **Additional Tips**

- **Case Sensitivity**:

  - By default, `contains` is case-insensitive.
  - Use `scontains` for case-sensitive searches.

- **Quoting Values**:

  - Enclose string values in double quotes `"..."`.
  - For numeric values, quotes are optional.

- **Combining Filters**:

  - Apply filters in multiple columns to narrow down your search.
  - Filters in different columns are combined using logical AND.

- **Handling Special Characters**:

  - If your search value includes special characters (like parentheses, asterisks, etc.), you may need to use regex patterns or escape them.

- **Understanding Filter Logic**:

  - The dashboard processes filters using the specified operators.
  - Incorrect syntax may result in no data being displayed.

---

If you have any questions or need assistance with filtering, please refer to this guide or contact support.

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


# Callbacks for opening and closing the modal
@app.callback(
    Output("fasstmasst-modal", "is_open"),
    [Input("open-fasstmasst-button", "n_clicks"), Input("submit-fasstmasst", "n_clicks")],
    [State("fasstmasst-modal", "is_open")],
)
def toggle_modal(open_click, submit_click, is_open):
    if open_click or submit_click:
        return not is_open
    return is_open


# Callback to render the appropriate page
@app.callback(Output('page-content', 'children'),
              [Input('url', 'pathname')])
def display_page(pathname):
    if pathname == '/documentation':
        return documentation_layout
    else:
        return panredu_layout


@app.callback(
    Output("download-complete-tsv", "data"),
    Input("download-complete-link", "n_clicks"),
    prevent_initial_call=True
)
def download_df(n_clicks):
    return dcc.send_data_frame(df.to_csv, "redu_complete.tsv", sep="\t", index=False)


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
@app.callback(
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
        print("Reset filters button clicked")
        return '', 'No filters applied.'

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


@app.callback(
    Output("filtered-data-store", "data"),
    Input("url", "pathname"),
    Input("data-table", "filter_query"),
    Input("submit-fasstmasst", "n_clicks"),
    State("filtered-data-store", "data"),
    State("usi", "value"),
    State("min-cosine", "value"),
    State("min-matching-peaks", "value"),
    State("fragment-tolerance", "value"),
    State("precursor-tolerance", "value"),
    prevent_initial_call=False
)
def update_filtered_data_store(pathname, filter_query, submit_n_clicks, current_data, usi, min_cos, min_fragments,
                               fragment_mz_tol, precursor_mz_tol):
    ctx = callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]

    # Initialize dff with full dataset for fallback
    dff = df.copy() if not current_data else pd.DataFrame(current_data)

    # Initial load with full dataset
    if triggered_id == "url":
        print("Loading full dataset on initial load.")
        dff = df.copy()

    # Filter via data-table filter_query
    elif triggered_id == "data-table":
        if filter_query:
            filtering_expressions = filter_query.split(' && ')
            for filter_part in filtering_expressions:
                col_name, operator, value = split_filter_part(filter_part)
                if operator and col_name in dff.columns:
                    # Apply the operator logic
                    if operator == 'contains':
                        dff = dff[dff[col_name].astype(str).str.contains(value, case=False, na=False, regex=True)]
                    elif operator == 'scontains':
                        dff = dff[dff[col_name].astype(str).str.contains(value, case=True, na=False, regex=True)]
                    elif operator == '=':
                        dff = dff[dff[col_name] == value]
                    elif operator == '!=':
                        dff = dff[dff[col_name] != value]
                    elif operator == '<':
                        dff = dff[pd.to_numeric(dff[col_name], errors='coerce') < float(value)]
                    elif operator == '<=':
                        dff = dff[pd.to_numeric(dff[col_name], errors='coerce') <= float(value)]
                    elif operator == '>':
                        dff = dff[pd.to_numeric(dff[col_name], errors='coerce') > float(value)]
                    elif operator == '>=':
                        dff = dff[pd.to_numeric(dff[col_name], errors='coerce') >= float(value)]
                    elif operator == 'in':
                        values = [v.strip() for v in value.split(',')]
                        dff = dff[dff[col_name].isin(values)]
                    elif operator == 'nin':
                        values = [v.strip() for v in value.split(',')]
                        dff = dff[~dff[col_name].isin(values)]
                print(f"Filtered {col_name} with {operator} {value}. Rows remaining: {len(dff)}")
        else:
            print("No filter applied in data-table; displaying full data set.")

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
                    dff = dff[dff['USI'].isin(matching_usis)]
                    print("Filtered rows after USI subset:", len(dff))  # Debug

        except Exception as e:
            print(f"Error during API request: {e}")
            return []

    # Return the fully filtered dataset for storage
    return dff.to_dict('records')



# Continue with other callbacks
@app.callback(
    Output("data-table", "data"),
    Output("rows-remaining", "children"),
    Output("page-count", "children"),
    Input("filtered-data-store", "data"),
    Input("data-table", "page_current"),
    Input("data-table", "page_size"),
    Input("data-table", "sort_by"),
    prevent_initial_call=True
)
def update_table_display(filtered_data, page_current, page_size, sort_by):
    dff = pd.DataFrame(filtered_data)

    # Sorting
    if sort_by:
        dff = dff.sort_values(
            [col['column_id'] for col in sort_by],
            ascending=[col['direction'] == 'asc' for col in sort_by],
            inplace=False
        )

    # Pagination
    total_filtered_rows = len(dff)
    total_pages = max(1, math.ceil(total_filtered_rows / page_size))
    page_info = f"Page {page_current + 1} of {total_pages}"
    rows_remaining_text = f"{total_filtered_rows} files remaining"

    # Slice data based on current page
    start_idx = page_current * page_size
    end_idx = start_idx + page_size
    paginated_data = dff.iloc[start_idx:end_idx].to_dict('records')

    return paginated_data, rows_remaining_text, page_info



@app.callback(
    Output("download-dataframe-csv", "data"),
    Input("download-button", "n_clicks"),
    State('filtered-data-store', 'data'),
    prevent_initial_call=True,
)
def download_filtered_data(n_clicks, filtered_data):
    if n_clicks is None:
        raise PreventUpdate

    dff = pd.DataFrame(filtered_data)
    print("Downloading data with rows:", len(dff))

    return dcc.send_data_frame(dff.to_csv, "filtered_dataset.csv", index=False)


import clipboard
@app.callback(
    Output("clipboard-content-store", "data"),
    Input("copy-button", "n_clicks"),
    State("filtered-data-store", "data"),
    prevent_initial_call=True,
)
def update_clipboard_content(n_clicks, filtered_data):
    if n_clicks:
        usis = [row['USI'] for row in filtered_data if 'USI' in row]
        usi_text = '\n'.join(usis)
        print(f"USIs copied to clipboard: {usi_text}")
        clipboard.copy(usi_text)
        return usi_text
    return ''



if __name__ == '__main__':
    app.run_server(debug=True)