import os
import dash
from dash import dcc, html, dash_table, Input, Output, State, ALL, callback_context
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
import pandas as pd
import numpy as np
import re
import math
import json
import threading
import urllib.parse
from collections import OrderedDict

from app import app

import config
from utils import _load_redu_sampledata, _metadata_last_modified, _metadata_mtime
from version_utils import get_versions


# How many files can be handed to a GNPS2 workflow from one selection. The USIs travel
# in the URL hash, so this keeps the generated links to a size browsers accept.
MAX_SELECTION = 500

GNPS2_NETWORKING_URL = "https://gnps2.org/workflowinput?workflowname=classical_networking_workflow"
GNPS2_MASSQL_URL = "https://gnps2.org/workflowinput?workflowname=massql_workflow"
GNPS2_DASHBOARD_URL = "https://dashboard.gnps2.org/"

MZML_CONDITION = '{USI} contains ".(mzML|mzXML)$"'

# Example filters. Each one replaces the current filter and makes sure the columns it
# filters on are visible, so the user can see why rows matched.
PRESETS = [
    {"label": "Human samples",
     "query": '{NCBITaxonomy} contains "Homo sapiens"'},
    {"label": "Plant samples",
     "query": '{SampleType} = "plant"'},
    {"label": "Orbitrap instruments",
     "query": '{MassSpectrometer} contains "(Orbitrap|Exactive|Exploris|Astral)"'},
    {"label": "Human & mouse genus, not Mus musculus",
     "query": '{NCBITaxonomy} contains "(Homo|Mus)(?!.*musculus)"'},
    {"label": "Rat blood",
     "query": '{UBERONBodyPartName} contains "blood" && {NCBITaxonomy} contains "Rattus norvegicus"'},
    {"label": "Lipidomics: RP-LC, hydrophobic extraction, has MS2",
     "query": '{ChromatographyAndPhase} contains "reverse phase" && {SampleExtractionMethod} contains "(butanol|dichloromethane|isopropanol|methyltertbutylether)" && {MS2spectra_count} > 0'},
    {"label": "Isolated from plants",
     "query": '{IsolationSourceNCBIKingdom} = "Viridiplantae"'},
]

OPERATOR_OPTIONS = [
    {"label": "is", "value": "="},
    {"label": "is not", "value": "!="},
    {"label": "contains (regex)", "value": "contains"},
    {"label": ">", "value": ">"},
    {"label": ">=", "value": ">="},
    {"label": "<", "value": "<"},
    {"label": "<=", "value": "<="},
]


##############################
# Filtering
##############################

class FilterError(Exception):
    pass


# A file of several organisms (a co-culture, a host with its parasite, a mixture, a pool of several species) has one
# NCBITaxonomy term per organism, joined by '||' ('6613|Euprymna scolopes||312309|Aliivibrio fischeri ES114'), and
# the NCBI rank / division / lineage columns and OpenTreeOfLifeTaxonomyID one value per organism in the same order;
# so do IsolationSourceNCBITaxonomy (the organisms an isolate was isolated from) and its NCBI kingdom / phylum.
# In these columns "is" / "is not" compare a value with the cell and with each of its organisms, the suggestions and
# the overview count organisms, and a "contains" value with '||' is read as it is written.
MULTI_SEP = '||'


def _is_multi_value_column(col_name):
    return str(col_name).startswith(('NCBI', 'IsolationSourceNCBI')) or col_name == 'OpenTreeOfLifeTaxonomyID'


def _cell_parts(cell):
    """The organisms' values of a cell ('missing value' slots dropped), each once."""
    return list(dict.fromkeys(p.strip() for p in str(cell).split(MULTI_SEP) if p.strip() and p.strip() != 'missing value'))


def _cell_or_part_in(column, values):
    """Rows (bool array) whose cell is one of values or, for a cell of several organisms, has one of them as one
    of its organisms."""
    values = set(values)
    matches = column.isin(values).to_numpy().copy()
    as_text = column.astype(str)
    several = as_text.str.contains(MULTI_SEP, regex=False, na=False).to_numpy()
    if several.any():
        matches[several] = [any(p in values for p in _cell_parts(cell)) or cell in values for cell in as_text[several]]
    return matches


def _explode_parts(series):
    """The values of a Series with each cell of several organisms replaced by its organisms' values."""
    as_text = series.astype(str)
    several = as_text.str.contains(MULTI_SEP, regex=False, na=False)
    if not several.any():
        return series
    return pd.concat([series[~several], as_text[several].map(_cell_parts).explode().dropna()])


# Operators as the DataTable writes them. Case variants carry an "s" (sensitive) or
# "i" (insensitive) prefix and relational operators can also be typed as words
# ("eq plant" arrives as "seq plant"). Longest first, so ">=" is not read as ">".
_OPERATOR_ALIASES = {
    '>=': '>=', '<=': '<=', '!=': '!=', '>': '>', '<': '<', '=': '=',
    'ge': '>=', 'le': '<=', 'ne': '!=', 'gt': '>', 'lt': '<', 'eq': '=',
    'contains': 'contains', 'datestartswith': 'datestartswith',
}
_BINARY_FILTER = re.compile(
    r'^\{(?P<col_name>(?:[^{}\\]|\\.)+)\} (?:[si])?(?P<operator>'
    + '|'.join(re.escape(op) for op in sorted(_OPERATOR_ALIASES, key=len, reverse=True))
    + r') (?P<value>.+)$'
)
_UNARY_FILTER = re.compile(r'^\{(?P<col_name>(?:[^{}\\]|\\.)+)\} (?:[si])?is (?P<what>\w+)$')


def split_filter_part(filter_part):
    """Parse one DataTable filter expression into (column, operator, value), with the
    operator normalised to =, !=, <, <=, >, >=, contains, datestartswith or "is"."""
    filter_part = filter_part.strip()
    match = _BINARY_FILTER.match(filter_part)
    if match:
        value = match.group('value').strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'`":
            value = value[1:-1].replace('\\' + value[0], value[0])
        return match.group('col_name'), _OPERATOR_ALIASES[match.group('operator')], value
    match = _UNARY_FILTER.match(filter_part)
    if match:
        return match.group('col_name'), 'is', match.group('what')
    return None, None, None


def _split_query(filter_query):
    """Split on " && " outside of quoted values, so a value may itself contain "&&"."""
    if not filter_query:
        return []
    parts, current, quote, i = [], [], None, 0
    while i < len(filter_query):
        char = filter_query[i]
        if quote:
            current.append(char)
            if char == '\\' and i + 1 < len(filter_query):
                current.append(filter_query[i + 1])
                i += 1
            elif char == quote:
                quote = None
        elif char in "\"'`":
            quote = char
            current.append(char)
        elif filter_query.startswith(' && ', i):
            parts.append(''.join(current))
            current = []
            i += 3
        else:
            current.append(char)
        i += 1
    parts.append(''.join(current))
    return [part.strip() for part in parts if part.strip()]


def _join_query(parts):
    return ' && '.join(parts)


def _filter_redu_sampledata(redu_df, filter_query=None):
    """Apply a DataTable filter_query. Raises FilterError with a readable message for
    filters that cannot be applied (unknown column, bad regex, non-numeric comparison)."""
    mask = np.ones(len(redu_df), dtype=bool)

    for filter_part in _split_query(filter_query):
        col_name, operator, value = split_filter_part(filter_part)
        if operator is None:
            raise FilterError(f"Could not understand the filter: {filter_part}")
        if col_name not in redu_df.columns:
            raise FilterError(f"Unknown column: {col_name}")

        column = redu_df[col_name]
        is_numeric = pd.api.types.is_numeric_dtype(column)

        if operator == 'is':
            if value == 'blank':
                as_text = column.astype(str)
                mask &= (column.isna() | (as_text.str.strip() == '') | (as_text == 'missing value')).to_numpy()
                continue
            raise FilterError(f"'is {value}' filters are not supported, use 'is blank' or a comparison")

        if operator == 'contains':
            if MULTI_SEP in value:
                # a copied value of several organisms: as a regular expression '||' would be an empty alternative
                # that matches every row
                value = re.escape(value)
            try:
                re.compile(value)
            except re.error as e:
                raise FilterError(f"Invalid regular expression for {col_name}: {value} ({e})")
            mask &= column.astype(str).str.contains(value, case=False, na=False, regex=True).to_numpy()
        elif operator == 'datestartswith':
            mask &= column.astype(str).str.startswith(value, na=False).to_numpy()
        elif operator in ('=', '!='):
            if is_numeric:
                try:
                    matches = (column == float(value)).to_numpy()
                except ValueError:
                    raise FilterError(f"{col_name} is numeric, but '{value}' is not a number")
            elif _is_multi_value_column(col_name):
                # the cell, or one of the organisms of a cell of several
                matches = _cell_or_part_in(column, [value])
            else:
                matches = (column == value).to_numpy()
            mask &= matches if operator == '=' else ~matches
        else:
            try:
                number = float(value)
            except ValueError:
                raise FilterError(f"'{operator}' needs a number, got '{value}' for {col_name}")
            numeric = pd.to_numeric(column, errors='coerce')
            if operator == '<':
                mask &= (numeric < number).to_numpy()
            elif operator == '<=':
                mask &= (numeric <= number).to_numpy()
            elif operator == '>':
                mask &= (numeric > number).to_numpy()
            elif operator == '>=':
                mask &= (numeric >= number).to_numpy()

    return redu_df[mask]


# Paging through a large result re-runs the same filter and sort, so the resulting row
# order is memoised per (data version, filter, sort).
_result_cache = OrderedDict()
_result_cache_lock = threading.Lock()
_RESULT_CACHE_SIZE = 16


def _filtered_sorted_positions(filter_query, sort_by):
    key = (_metadata_mtime(), filter_query or "", json.dumps(sort_by or []))
    with _result_cache_lock:
        if key in _result_cache:
            _result_cache.move_to_end(key)
            return _result_cache[key]

    df_redu = _load_redu_sampledata()
    df = _filter_redu_sampledata(df_redu, filter_query)
    sort_by = [col for col in (sort_by or []) if col['column_id'] in df.columns]
    if sort_by:
        df = df.sort_values(
            [col['column_id'] for col in sort_by],
            ascending=[col['direction'] == 'asc' for col in sort_by],
            kind='stable',
            key=_sort_key,
            na_position='last',
        )
    positions = df_redu.index.get_indexer(df.index)

    with _result_cache_lock:
        _result_cache[key] = positions
        while len(_result_cache) > _RESULT_CACHE_SIZE:
            _result_cache.popitem(last=False)
    return positions


def _is_numeric_valued(column):
    """Whether a text column holds only numbers apart from 'missing value' (AgeInYears, BodyMassIndex, ...), over
    the whole table."""
    def compute():
        df = _load_redu_sampledata()
        if column not in df.columns or df[column].dtype != object:
            return False
        values = pd.Series(df[column].dropna().unique())
        values = values[values != 'missing value']
        return bool(len(values)) and bool(pd.to_numeric(values, errors='coerce').notna().all())
    return _cached_by_data_version("numeric-valued:" + str(column), compute)


# Numbers that stand for "not known" (MS2spectra_count -1: the file is not in the dataset cache; AgeInYears -1 / -1.0):
# they sort with 'missing value'. Negative numbers of other columns (depths, times before an event) are real values.
SORT_PLACEHOLDERS = {'MS2spectra_count': -1, 'AgeInYears': -1}


def _sort_key(values):
    """Columns of numbers kept as text sort by their numbers ("9.0" before "10.0"), with 'missing value' and the
    placeholder numbers last in both directions (as NaN); the cells themselves stay as they are."""
    key = values
    if values.dtype == object and _is_numeric_valued(values.name):
        key = pd.to_numeric(values, errors='coerce')
    if values.name in SORT_PLACEHOLDERS:
        numbers = key if pd.api.types.is_numeric_dtype(key) else pd.to_numeric(values, errors='coerce')
        # ('missing value' too: already NaN above, but not if the column ever holds other text and sorts as text)
        key = key.where((numbers != SORT_PLACEHOLDERS[values.name]) & (values != 'missing value'))
    return key


def _columns_in_query(filter_query):
    columns = []
    for part in _split_query(filter_query):
        col_name, _, _ = split_filter_part(part)
        if col_name and col_name not in columns:
            columns.append(col_name)
    return columns


def _quote(value):
    return '"' + str(value).replace('"', '\\"') + '"'


##############################
# Cached summaries
##############################

_summary_cache = {}


def _cached_by_data_version(name, compute, also_path=None):
    # also_path: a file the value is read from besides the table; its version is part of the key too
    mtime = _metadata_mtime()
    if also_path:
        try:
            stat = os.stat(also_path)
            mtime = (mtime, stat.st_mtime, stat.st_size)
        except OSError:
            mtime = (mtime, None)
    cached = _summary_cache.get(name)
    if cached and cached[0] == mtime:
        return cached[1]
    value = compute()
    _summary_cache[name] = (mtime, value)
    return value


def _real_values(series):
    return series[series.notna() & (series != 'missing value')]


def _compute_overview():
    """Summary numbers for the header tiles and the "What's in ReDU" panel. Every entry is
    optional: a statistic whose columns are not in the current metadata is left out."""
    df = _load_redu_sampledata()
    has = lambda *cols: all(col in df.columns for col in cols)

    def _subject_stats(mask):
        subset = df[mask]
        stats = [("Files", len(subset))]
        if has('UBERONBodyPartName'):
            stats.append(("Body parts", _real_values(subset['UBERONBodyPartName']).nunique()))
        if has('DOIDCommonName'):
            stats.append(("Diseases", _real_values(subset['DOIDCommonName']).nunique()))
        return stats

    overview = {"files": len(df), "sections": []}

    if has('ATTRIBUTE_DatasetAccession'):
        overview["datasets"] = df['ATTRIBUTE_DatasetAccession'].nunique()
    if has('NCBITaxonomy'):
        # (a file of several organisms counts each of them)
        overview["taxa"] = _real_values(_explode_parts(df['NCBITaxonomy'])).nunique()

    if has('DataSource'):
        sources = df['DataSource'].value_counts()
        overview["repositories"] = len(sources)
        overview["sections"].append(("Files by repository", list(sources.items()), True))

    if has('NCBIDivision', 'NCBITaxonomy'):
        pairs = df.loc[df['NCBIDivision'].notna() & (df['NCBIDivision'] != 'missing value'), ['NCBIDivision', 'NCBITaxonomy']]
        several = pairs['NCBITaxonomy'].astype(str).str.contains(MULTI_SEP, regex=False, na=False)
        if several.any():
            # files of several organisms: each organism with its division (the two cells hold them in the same order)
            split = [(d.strip(), t.strip())
                     for division, taxon in zip(pairs.loc[several, 'NCBIDivision'].astype(str), pairs.loc[several, 'NCBITaxonomy'].astype(str))
                     if division.count(MULTI_SEP) == taxon.count(MULTI_SEP)
                     for d, t in zip(division.split(MULTI_SEP), taxon.split(MULTI_SEP)) if d.strip() != 'missing value']
            pairs = pd.concat([pairs[~several], pd.DataFrame(split, columns=['NCBIDivision', 'NCBITaxonomy'])])
        divisions = (
            pairs.groupby('NCBIDivision')['NCBITaxonomy'].nunique()
            .sort_values(ascending=False)
        )
        overview["sections"].append(("Taxa by NCBI division",
                                     [(division, count) for division, count in divisions.items() if count >= 10], True))

    if has('NCBITaxonomy'):
        # (files with the organism, also among others: a pooled QC of human and other milk)
        overview["sections"].append(("Human (Homo sapiens)",
                                     _subject_stats(_cell_or_part_in(df['NCBITaxonomy'], ['9606|Homo sapiens'])), False))
        # (the genus, Mus musculus and its subspecies in the table)
        mouse = ['10088|Mus', '10095|Mus sp.', '10090|Mus musculus', '10092|Mus musculus domesticus']
        overview["sections"].append(("Mouse (Mus)", _subject_stats(_cell_or_part_in(df['NCBITaxonomy'], mouse)), False))

    if has('ENVOEnvironmentMaterial'):
        env_counts = df['ENVOEnvironmentMaterial'].value_counts().to_dict()
        # (the ENVO water, sediment and soil terms of the table, by name; any other material counts as "Other")
        env_groups = OrderedDict([
            ("Surface water", ['river water', 'surface water', 'ocean water', 'sea water', 'coastal sea water',
                               'pond water', 'fresh water', 'lake water', 'ditch water']),
            ("Groundwater", ['groundwater', 'interstitial water']),
            ("Waste water", ['waste water', 'industrial wastewater', 'treated wastewater']),
            ("Sediment / soil", ['sediment', 'soil', 'lake sediment', 'marine sediment',
                                 'stream sediment', 'deep marine sediment', 'sediment permeated by saline water',
                                 'peat soil', 'alpine soil', 'agricultural soil', 'volcanic soil', 'burned soil',
                                 'forest soil', 'dry soil', 'grassland soil']),
        ])
        grouped = [key for keys in env_groups.values() for key in keys]
        environment = [(label, sum(env_counts.get(k, 0) for k in keys)) for label, keys in env_groups.items()]
        environment.append(("Other", sum(count for key, count in env_counts.items()
                                         if key not in grouped and key != 'missing value')))
        overview["sections"].append(("Environmental samples", environment, True))

    return overview


def _repository_updates():
    """{repository: (last update, whether the last run updated it)} from the workflow's source_summary.tsv next to
    the table; {} when it is missing, cannot be read or has no last update (from an earlier workflow version). Also
    keyed by the summary's version: the workflow publishes it just after the table."""
    def compute():
        try:
            summary = pd.read_csv(config.PATH_TO_SOURCE_SUMMARY_FILE, sep='\t', dtype=str, keep_default_na=False)
        except Exception:
            return {}
        if not {'DataSource', 'last_update', 'last_run_status'} <= set(summary.columns):
            return {}
        # last_run_status: 'updated' or 'not updated', with the reason in parentheses
        return {row.DataSource: (row.last_update, row.last_run_status.split(' (')[0] == 'updated')
                for row in summary.itertuples() if row.last_run_status}
    return _cached_by_data_version("repository-updates", compute, also_path=config.PATH_TO_SOURCE_SUMMARY_FILE)


def _update_note(update):
    """The line under a repository in "Files by repository": the day its rows were last updated (the start of that
    workflow run, in the time zone of the "last updated" tile), or that the last run did not update it and the day
    its rows are from"""
    if update is None:
        return None
    last_update, updated = update
    when = pd.to_datetime(last_update, utc=True, errors='coerce') if last_update else pd.NaT
    when = None if pd.isna(when) else when.tz_convert('US/Pacific')
    title = when.strftime("%Y-%m-%d %H:%M %Z") if when is not None else None
    if updated:
        text = "updated " + when.strftime("%Y-%m-%d") if when is not None else "updated"
        return html.Div(text, className="redu-stat-note", title=title)
    text = "not updated in the last run" + ("; data from " + when.strftime("%Y-%m-%d") if when is not None else "")
    return html.Div(text, className="redu-stat-note redu-stat-note-stale", title=title)


def _column_suggestions(column):
    def compute():
        df = _load_redu_sampledata()
        if column not in df.columns:
            return []
        values = df[column].astype(str)
        if _is_multi_value_column(column):
            # a file of several organisms counts for each of them
            values = _explode_parts(values)
        counts = values.value_counts().head(300)
        return [(value, count) for value, count in counts.items()]
    return _cached_by_data_version("suggestions:" + column, compute)


##############################
# Layout
##############################

# Columns come from whatever the current metadata file contains, so columns added to or
# removed from the workflow output show up without code changes. These are only
# preferences: any that are missing are skipped.
PREFERRED_DEFAULT_COLUMNS = ["SampleType", "SampleTypeSub1", "NCBITaxonomy", "UBERONBodyPartName", "MassSpectrometer", "USI"]


def _all_columns():
    columns = list(_load_redu_sampledata().columns)
    preferred = [col for col in PREFERRED_DEFAULT_COLUMNS if col in columns]
    return preferred + [col for col in columns if col not in preferred]


def _default_columns():
    columns = _all_columns()
    preferred = [col for col in PREFERRED_DEFAULT_COLUMNS if col in columns]
    return preferred or columns[:6]


def _numeric_columns():
    df = _load_redu_sampledata()
    return [col for col in df.columns if pd.api.types.is_numeric_dtype(df[col])]


def _has_values(column):
    """Whether a column has a value other than 'missing value' (a new column may have none yet)"""
    def compute():
        values = _load_redu_sampledata()[column]
        return bool((values.notna() & (values != 'missing value')).any())
    return _cached_by_data_version("has-values:" + str(column), compute)


def _available_presets():
    # (an example on a column without values would show no files)
    columns = set(_all_columns())
    return [(i, preset) for i, preset in enumerate(PRESETS)
            if set(_columns_in_query(preset["query"])) <= columns
            and all(_has_values(column) for column in _columns_in_query(preset["query"]))]


# Warm the cache at startup so the first visitor does not pay for loading the table
_load_redu_sampledata()

dash_app = dash.Dash(
    name="redu_selection",
    server=app,
    url_base_pathname="/selection/",
    assets_folder=os.path.join(os.path.dirname(os.path.realpath(__file__)), "assets"),
    external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.BOOTSTRAP],
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)

dash_app.config.suppress_callback_exceptions = True
dash_app.title = 'ReDU2'


def _external_link(label, href, icon=None):
    children = [html.I(className=f"bi bi-{icon} me-1")] if icon else []
    return dbc.NavItem(dbc.NavLink(children + [label], href=href, target="_blank", external_link=True))


navbar = dbc.Navbar(
    dbc.Container([
        html.A(
            html.Img(src=dash_app.get_asset_url("panReDU_logo.png"), height="48px", alt="Pan-ReDU"),
            href="/",
            className="navbar-brand",
        ),
        dbc.NavbarToggler(id="navbar-toggler"),
        dbc.Collapse(
            dbc.Nav([
                _external_link("Documentation", "https://wang-bioinformatics-lab.github.io/GNPS2_Documentation/ReDU_overview/", "book"),
                _external_link("Column descriptions", "https://docs.google.com/spreadsheets/d/10U0xnJUKa_mD0H_9suH1KJAlJD9io9e4chBX8EAHneE/edit?usp=sharing", "table"),
                _external_link("Contribute metadata", "https://deposit.redu.gnps2.org/", "cloud-upload"),
                dbc.NavItem(dbc.NavLink([html.I(className="bi bi-download me-1"), "Download complete ReDU"],
                                        href="/dump", external_link=True)),
            ], className="ms-auto", navbar=True),
            id="navbar-collapse",
            navbar=True,
        ),
    ], fluid=True),
    className="redu-navbar",
    color="light",
    expand="lg",
)


def _repository_links():
    links = [
        ("MetaboLights", "https://www.ebi.ac.uk/metabolights/"),
        ("Metabolomics Workbench", "https://www.metabolomicsworkbench.org/"),
        ("GNPS/MassIVE", "https://gnps.ucsd.edu/ProteoSAFe/datasets.jsp#%7B%22query%22%3A%7B%7D%2C%22table_sort_history%22%3A%22createdMillis_dsc%22%2C%22title_input%22%3A%22GNPS%22"),
        ("NORMAN/DSFP", "https://dsfp.norman-data.eu/search"),
    ]
    children = []
    for i, (label, href) in enumerate(links):
        if i:
            children.append(", " if i < len(links) - 1 else " and ")
        children.append(html.A(label, href=href, target="_blank"))
    return children


header = dbc.Container([
    html.H1("Pan-ReDU", className="redu-title"),
    html.P(
        ["Harmonized sample metadata for public untargeted metabolomics files from "]
        + _repository_links()
        + [". Updated daily. Find files, then download them or send them to GNPS2 for analysis. ",
           html.A("Contribute your data", href="https://deposit.redu.gnps2.org/", target="_blank"),
           " to grow the resource."],
        className="redu-lead",
    ),
    html.Div(id="overview-tiles", className="redu-tiles"),
    html.Div(id="overview-details", className="redu-stats"),
], fluid=True, className="redu-header")


def _filter_panel():
    return dbc.Card([
        dbc.CardHeader(html.Span([html.I(className="bi bi-funnel me-2"), "Filters"])),
        dbc.CardBody([
            html.Div(id="filter-notice"),
            html.Div(id="active-filters"),
            dbc.Button("Clear all filters", id="clear-filters", color="link", size="sm", className="p-0 mt-1"),
            html.Div(className="mb-3"),

            html.Div("Add a filter", className="redu-section-label"),
            dcc.Dropdown(
                id="builder-column",
                options=[{"label": col, "value": col} for col in sorted(_all_columns(), key=str.lower)],
                placeholder="Column...",
                clearable=False,
                className="mb-2",
            ),
            dbc.Row([
                dbc.Col(dbc.Select(id="builder-operator", options=OPERATOR_OPTIONS, value="="), width=5),
                dbc.Col(dbc.Input(id="builder-value", placeholder="Value...", list="builder-suggestions",
                                  debounce=False, autocomplete="off"), width=7),
            ], className="g-2 mb-2"),
            html.Datalist(id="builder-suggestions"),
            dbc.Button([html.I(className="bi bi-plus-lg me-1"), "Add filter"], id="builder-add",
                       color="primary", size="sm", className="w-100", disabled=True),
            dbc.FormText("Pick a value from the suggestions, or type a regular expression with \"contains\". "
                         "Files of several organisms list them separated by || (NCBITaxonomy, IsolationSourceNCBITaxonomy "
                         "and their NCBI columns); \"is\" matches each of them.",
                         className="d-block mt-1"),

            html.Hr(),
            html.Div("Examples", className="redu-section-label"),
            html.Div([
                dbc.Button(preset["label"], id={"type": "preset", "index": i}, color="light", size="sm",
                           className="redu-preset")
                for i, preset in _available_presets()
            ], className="d-flex flex-column gap-1"),
        ]),
    ], className="mb-3")


def _sidebar():
    return html.Div([_filter_panel()])


def _results_toolbar():
    has_usi = "USI" in _all_columns()
    return html.Div([
        html.Div([
            html.Div(id="result-count", className="redu-result-count"),
            html.Div(id="filter-error"),
        ], className="flex-grow-1"),
        html.Div([
            dbc.Button([html.I(className="bi bi-file-earmark-code me-1"), "mzML/mzXML only"],
                       id="subset-mzml-button", color="secondary", outline=True, size="sm",
                       title="Keep only open-format files, which GNPS2 tools can read directly",
                       style=None if has_usi else {"display": "none"}),
            dcc.Dropdown(
                id="visible-columns",
                options=[{"label": col, "value": col} for col in _all_columns()],
                value=_default_columns(),
                multi=True,
                clearable=False,
                placeholder="Columns",
                className="redu-column-picker",
            ),
            dbc.DropdownMenu([
                dbc.DropdownMenuItem("Metadata table (CSV)", id="download-button"),
                dbc.DropdownMenuItem("USI list (CSV)", id="USIdownload-button", disabled=not has_usi),
                dbc.DropdownMenuItem(divider=True),
                dbc.DropdownMenuItem("How to batch download raw files",
                                     href="https://github.com/Wang-Bioinformatics-Lab/downloadpublicdata",
                                     target="_blank", external_link=True),
            ], label=html.Span([html.I(className="bi bi-download me-1"), "Download"]),
               color="secondary", size="sm", align_end=True, toggle_class_name="redu-download-toggle"),
            dcc.Clipboard(id="share-link", title="Copy a link to this filtered view",
                          className="btn btn-outline-secondary btn-sm redu-share",
                          content=""),
        ], className="redu-toolbar-actions"),
    ], className="redu-toolbar")


def _selection_bar():
    return html.Div([
        html.Div([
            html.Span(id="selection-count", className="me-3"),
            dbc.Button("Select all matching", id="select-all-button", color="link", size="sm", className="p-0 me-3"),
            dbc.Button("Clear selection", id="clear-selection-button", color="link", size="sm", className="p-0"),
        ], className="d-flex align-items-center flex-wrap"),
        html.Div([
            dbc.Button([html.I(className="bi bi-eye me-1"), "View raw data"], id="dashboard-button",
                       color="primary", size="sm", href=GNPS2_DASHBOARD_URL, target="_blank", external_link=True),
            dbc.Button([html.I(className="bi bi-diagram-3 me-1"), "Molecular networking"], id="mn-button",
                       color="primary", size="sm", href=GNPS2_NETWORKING_URL, target="_blank", external_link=True),
            dbc.Button([html.I(className="bi bi-search me-1"), "MassQL search"], id="massql-button",
                       color="primary", size="sm", href=GNPS2_MASSQL_URL, target="_blank", external_link=True),
        ], className="d-flex gap-2 flex-wrap"),
    ], className="redu-selection-bar")


def _make_table(filter_query='', visible_columns=None, page_size=25, sort_by=None):
    """Build the results table.

    Filters set from outside the table (presets, filter builder, chips, URL) re-create it
    instead of only updating filter_query: the DataTable skips refreshing its per-column
    filter cells when the new query equals the last one it generated itself (e.g. ""),
    and the stale cells then come back the next time the user types in any filter cell.
    """
    all_columns = _all_columns()
    numeric_columns = _numeric_columns()
    visible_columns = [col for col in (visible_columns or []) if col in all_columns] or _default_columns()
    return dash_table.DataTable(
        id='data-table',
        columns=[
            {'name': col, 'id': col, 'type': 'numeric' if col in numeric_columns else 'text'}
            for col in all_columns
        ],
        hidden_columns=[col for col in all_columns if col not in visible_columns],
        data=[],
        page_current=0,
        page_size=page_size,
        page_action='custom',
        row_selectable='multiple' if 'USI' in all_columns else False,
        selected_rows=[],
        filter_action='custom',
        filter_query=filter_query,
        filter_options={"placeholder_text": "filter..."},
        sort_action='custom',
        sort_mode='multi',
        sort_by=sort_by or [],
        tooltip_delay=400,
        tooltip_duration=None,
        style_table={'overflowX': 'auto'},
        style_cell={
            'textAlign': 'left',
            'whiteSpace': 'nowrap',
            'overflow': 'hidden',
            'textOverflow': 'ellipsis',
            'maxWidth': '320px',
            'minWidth': '90px',
            'padding': '6px 10px',
            'fontFamily': 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
            'fontSize': '13px',
            'userSelect': 'text',
        },
        style_header={
            'backgroundColor': '#f1f4f9',
            'fontWeight': '600',
            'borderBottom': '2px solid #d5dce8',
        },
        style_filter={'backgroundColor': '#fbfcfe'},
        style_data_conditional=[{'if': {'row_index': 'odd'}, 'backgroundColor': '#fafbfd'}] + [
            {'if': {'filter_query': '{%s} = "missing value"' % col, 'column_id': col}, 'color': '#a0a7b4'}
            for col in all_columns if col not in numeric_columns
        ],
        cell_selectable=False,
    )


def _results_panel():
    return dbc.Card([
        dbc.CardBody([
            _results_toolbar(),
            dcc.Loading(html.Div(_make_table(), id="table-container"), type="dot", delay_show=300, color="#3b6fb6"),
            html.Div([
                html.Div(id="page-count", className="text-muted small"),
                html.Div([
                    html.Span("Rows per page", className="text-muted small me-2"),
                    dbc.Select(id="page-size", options=[{"label": str(n), "value": str(n)} for n in (10, 25, 50, 100)],
                               value="25", size="sm", style={"width": "80px"}),
                ], className="d-flex align-items-center"),
            ], className="d-flex justify-content-between align-items-center mt-2"),
            html.Hr(className="my-3"),
            _selection_bar(),
        ]),
    ])


footer = html.Footer(
    dbc.Container([
        html.Div([
            "Please cite: El Abiead Y., et al. Enabling pan-repository reanalysis for big data science of public metabolomics data. ",
            html.I("Nat Commun"), " 16, 4838 (2025). ",
            html.A("doi:10.1038/s41467-025-60067-y", href="https://doi.org/10.1038/s41467-025-60067-y", target="_blank"),
        ]),
        html.Div("Contributors: Yasin El Abiead, Mingxun Wang", className="mt-1"),
        html.Div(id="version-indicator", className="redu-version"),
    ], fluid=True),
    className="redu-footer",
)


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


# A function, so every page load picks up the columns of the current metadata file
def serve_layout():
    return html.Div([
        dcc.Location(id='url', refresh=False),
        # 'callback-nav' tells the 'url' Location about pushed URLs too, so going back to them works
        dcc.Location(id='url-write', refresh='callback-nav'),
        dcc.Store(id='selected-usis', data=[]),
        dcc.Download(id="download-dataframe-csv"),
        navbar,
        header,
        dbc.Container(
            dbc.Row([
                dbc.Col(_sidebar(), lg=3, md=4),
                dbc.Col(_results_panel(), lg=9, md=8),
            ], className="g-3"),
            fluid=True,
        ),
        footer,
    ])


dash_app.layout = serve_layout


##############################
# Callbacks
##############################

dash_app.clientside_callback(
    "function(n, is_open) { return n ? !is_open : is_open; }",
    Output("navbar-collapse", "is_open"),
    Input("navbar-toggler", "n_clicks"),
    State("navbar-collapse", "is_open"),
)


# Resolved on every page load rather than baked into the static layout, because the
# workflow lives on a bind mount and can be updated without restarting the container.
@dash_app.callback(
    Output("version-indicator", "children"),
    Input("url", "pathname")
)
def update_version_indicator(_pathname):
    versions = get_versions()

    def _commit_link(info):
        if info["short"] == "unknown":
            return html.Span("unknown")
        return html.A(info["short"], href=info["url"], target="_blank")

    return [
        html.Span("ReDU "),
        _commit_link(versions["redu"]),
        html.Span("  ·  metadata workflow "),
        _commit_link(versions["workflow"]),
    ]


def _tile(value, label):
    return html.Div([html.Div(value, className="redu-tile-value"), html.Div(label, className="redu-tile-label")],
                    className="redu-tile")


@dash_app.callback(
    Output("overview-tiles", "children"),
    Output("overview-details", "children"),
    Input("url", "pathname")
)
def update_overview(_pathname):
    overview = _cached_by_data_version("overview", _compute_overview)
    last_modified = _metadata_last_modified().strftime("%Y-%m-%d %H:%M %Z")
    updates = _repository_updates()

    tiles = [_tile(f"{overview['files']:,}", "files")]
    for key, label in (("datasets", "datasets"), ("taxa", "taxa"), ("repositories", "repositories")):
        if key in overview:
            tiles.append(_tile(f"{overview[key]:,}", label))
    tiles.append(_tile(last_modified, "last updated"))

    def _stat_row(label, value, share, note=None):
        cells = [html.Span(str(label), className="redu-stat-label", title=str(label)),
                 html.Span(f"{value:,}", className="redu-stat-value")]
        if share is not None:
            # Thin bar showing the value relative to the largest one in the card
            cells.append(html.Div(html.Div(style={"width": f"{share:.0%}"}), className="redu-stat-bar"))
        if note is not None:
            cells.append(note)
        return html.Div(cells, className="redu-stat-row")

    def _stat_card(title, rows, bars):
        largest = max((value for _, value in rows), default=0) or 1
        # (the repositories: when each was last updated)
        notes = updates if title == "Files by repository" else {}
        return html.Div([
            html.Div(title, className="redu-stat-title"),
            html.Div([_stat_row(label, value, value / largest if bars else None, _update_note(notes.get(label)))
                      for label, value in rows],
                     className="redu-stat-rows"),
        ], className="redu-stat-card")

    details = [_stat_card(title, rows, bars) for title, rows, bars in overview["sections"] if rows]
    return tiles, details


@dash_app.callback(
    Output("builder-suggestions", "children"),
    Output("builder-operator", "value"),
    Output("builder-value", "value"),
    Input("builder-column", "value"),
    prevent_initial_call=True,
)
def update_builder_suggestions(column):
    if not column:
        raise PreventUpdate
    options = [html.Option(value=value, label=f"{count:,} files") for value, count in _column_suggestions(column)]
    operator = ">" if column in _numeric_columns() else "="
    return options, operator, ""


@dash_app.callback(
    Output("builder-add", "disabled"),
    Input("builder-column", "value"),
    Input("builder-value", "value"),
)
def toggle_builder_add(column, value):
    return not (column and value and value.strip())


def _show_columns(visible, columns):
    all_columns = _all_columns()
    # Drop columns that no longer exist (e.g. a tab opened before the metadata changed)
    visible = [col for col in (visible or []) if col in all_columns]
    for col in columns:
        if col in all_columns and col not in visible:
            visible.append(col)
    return visible


# Every control that rewrites the filter goes through this one callback, so the
# DataTable's filter_query stays the single source of truth for what is applied.
def _drop_unknown_columns(filter_query):
    """Remove filter parts on columns the current metadata does not have (e.g. from a
    bookmark made before a column was removed). The DataTable throws on those."""
    all_columns = set(_all_columns())
    kept, dropped = [], []
    for part in _split_query(filter_query):
        col_name, _, _ = split_filter_part(part)
        if col_name is not None and col_name not in all_columns:
            dropped.append(col_name)
        else:
            kept.append(part)
    return _join_query(kept), dropped


@dash_app.callback(
    Output("table-container", "children"),
    Output("visible-columns", "value"),
    Output("filter-notice", "children"),
    Input("url", "search"),
    Input("subset-mzml-button", "n_clicks"),
    Input({"type": "preset", "index": ALL}, "n_clicks"),
    Input({"type": "remove-filter", "index": ALL}, "n_clicks"),
    Input("clear-filters", "n_clicks"),
    Input("builder-add", "n_clicks"),
    Input("builder-value", "n_submit"),
    State("builder-column", "value"),
    State("builder-operator", "value"),
    State("builder-value", "value"),
    State("data-table", "filter_query"),
    State("data-table", "page_size"),
    State("data-table", "sort_by"),
    State("visible-columns", "value"),
)
def update_filters(search, _mzml, _presets, _removes, _clear, _add, _submit,
                   builder_column, builder_operator, builder_value,
                   filter_query, page_size, sort_by, visible_columns):
    ctx = callback_context
    triggered = ctx.triggered_id
    parts = _split_query(filter_query)

    if triggered is None or triggered == "url":
        params = urllib.parse.parse_qs((search or "").lstrip("?"))
        new_query = params.get("filter", [""])[0]
        if _split_query(new_query) == _split_query(filter_query):
            raise PreventUpdate
    elif not ctx.triggered[0]["value"]:
        # Pattern-matching inputs fire when their components are (re)created
        raise PreventUpdate
    elif triggered == "subset-mzml-button":
        if MZML_CONDITION not in parts:
            parts.append(MZML_CONDITION)
        new_query = _join_query(parts)
    elif triggered == "clear-filters":
        new_query = ""
    elif triggered in ("builder-add", "builder-value"):
        if not (builder_column and builder_value and builder_value.strip()):
            raise PreventUpdate
        part = "{%s} %s %s" % (builder_column, builder_operator or "=", _quote(builder_value))
        if part not in parts:
            parts.append(part)
        new_query = _join_query(parts)
    elif triggered["type"] == "preset":
        new_query = PRESETS[triggered["index"]]["query"]
    elif triggered["type"] == "remove-filter":
        index = triggered["index"]
        parts = [part for i, part in enumerate(parts) if i != index]
        new_query = _join_query(parts)
    else:
        raise PreventUpdate

    new_query, dropped = _drop_unknown_columns(new_query)
    notice = None
    if dropped:
        notice = dbc.Alert(
            [html.I(className="bi bi-info-circle me-2"),
             "Ignored filters on columns that are no longer in ReDU: " + ", ".join(dropped)],
            color="info", dismissable=True, className="py-1 px-2 small mb-2",
        )

    visible_columns = _show_columns(visible_columns, _columns_in_query(new_query))
    return _make_table(new_query, visible_columns, page_size, sort_by), visible_columns, notice


@dash_app.callback(
    Output("data-table", "hidden_columns"),
    Input("visible-columns", "value"),
)
def update_hidden_columns(visible_columns):
    # With nothing picked the table would be empty, so fall back to the default columns
    visible_columns = visible_columns or _default_columns()
    return [col for col in _all_columns() if col not in visible_columns]


_OPERATOR_LABELS = {"=": "is", "!=": "is not", "contains": "contains", "is": "is"}


@dash_app.callback(
    Output("active-filters", "children"),
    Output("clear-filters", "style"),
    Output("url-write", "search"),
    Input("data-table", "filter_query"),
)
def update_active_filters(filter_query):
    parts = _split_query(filter_query)
    search = "?" + urllib.parse.urlencode({"filter": filter_query}) if parts else ""
    if callback_context.triggered_id is None:
        # Initial page load: the table has not read the filter from the URL yet, so writing
        # its empty filter back would wipe out a shared link
        search = dash.no_update

    if not parts:
        return html.Div("No filters applied, showing all files.", className="text-muted small"), {"display": "none"}, search

    chips = []
    for i, part in enumerate(parts):
        col_name, operator, value = split_filter_part(part)
        if operator is None:
            label = part
        else:
            label = [html.Strong(col_name), f" {_OPERATOR_LABELS.get(operator, operator)} ", html.Span(value, className="redu-chip-value")]
        chips.append(html.Div([
            html.Span(label, className="redu-chip-label", title=part),
            html.Button(html.I(className="bi bi-x"), id={"type": "remove-filter", "index": i},
                        className="redu-chip-remove", title="Remove this filter"),
        ], className="redu-chip"))

    return html.Div(chips, className="d-flex flex-column gap-1"), {}, search


dash_app.clientside_callback(
    "function(n) { return n ? window.location.href : ''; }",
    Output("share-link", "content"),
    Input("share-link", "n_clicks"),
    prevent_initial_call=True,
)


@dash_app.callback(
    Output("data-table", "page_size"),
    Input("page-size", "value"),
)
def update_page_size(page_size):
    return int(page_size or 25)


def _usis_on_page(data):
    return [row.get("USI") for row in data or []]


def _count_phrase(n_files, positions, df_redu):
    count = [html.Strong(f"{n_files:,}"), " files"]
    if n_files and 'ATTRIBUTE_DatasetAccession' in df_redu.columns:
        n_datasets = df_redu['ATTRIBUTE_DatasetAccession'].iloc[positions].nunique()
        count += [" from ", html.Strong(f"{n_datasets:,}"), " datasets"]
    return count


@dash_app.callback(
    Output("data-table", "data"),
    Output("data-table", "selected_rows"),
    Output("data-table", "page_current"),
    Output("data-table", "page_count"),
    Output("data-table", "tooltip_data"),
    Output("result-count", "children"),
    Output("page-count", "children"),
    Output("filter-error", "children"),
    Input("data-table", "page_current"),
    Input("data-table", "page_size"),
    Input("data-table", "sort_by"),
    Input("data-table", "filter_query"),
    State("selected-usis", "data"),
)
def update_table_display(page_current, page_size, sort_by, filter_query, selected_usis):
    df_redu = _load_redu_sampledata()

    try:
        positions = _filtered_sorted_positions(filter_query, sort_by)
        error = None
    except FilterError as e:
        positions = np.arange(0)
        error = dbc.Alert([html.I(className="bi bi-exclamation-triangle me-2"), str(e)],
                          color="warning", className="py-1 px-2 mt-2 mb-0 small")

    # A new filter or page size starts over at the first page; otherwise the user can be
    # left on a page past the end of a smaller result.
    triggered = {t["prop_id"] for t in callback_context.triggered}
    if {"data-table.filter_query", "data-table.page_size", "data-table.sort_by"} & triggered:
        page_current = 0

    page_size = page_size or 25
    total_rows = len(positions)
    total_pages = max(1, math.ceil(total_rows / page_size))
    page_current = min(page_current or 0, total_pages - 1)

    page_positions = positions[page_current * page_size:(page_current + 1) * page_size]
    page_df = df_redu.iloc[page_positions]
    page_data = page_df.to_dict('records')

    selected = set(selected_usis or [])
    selected_rows = [i for i, row in enumerate(page_data) if row.get("USI") is not None and row.get("USI") in selected]

    tooltip_data = [
        {col: {'value': str(value), 'type': 'text'} for col, value in row.items() if len(str(value)) > 40}
        for row in page_data
    ]

    if error is None:
        count = _count_phrase(total_rows, positions, df_redu)
        if _split_query(filter_query):
            count.append(html.Span(" match your filters", className="text-muted"))
    else:
        count = [html.Strong("0"), " files"]

    page_info = f"Page {page_current + 1:,} of {total_pages:,}"

    return page_data, selected_rows, page_current, total_pages, tooltip_data, count, page_info, error


@dash_app.callback(
    Output("selected-usis", "data"),
    Input("data-table", "selected_rows"),
    State("data-table", "data"),
    State("selected-usis", "data"),
    prevent_initial_call=True,
)
def track_selection(selected_rows, data, selected_usis):
    page_usis = _usis_on_page(data)
    on_page = set(page_usis)
    kept = [usi for usi in (selected_usis or []) if usi not in on_page]
    newly = [page_usis[i] for i in (selected_rows or []) if i < len(page_usis) and page_usis[i] is not None]
    return (kept + newly)[:MAX_SELECTION]


@dash_app.callback(
    Output("selected-usis", "data", allow_duplicate=True),
    Output("data-table", "selected_rows", allow_duplicate=True),
    Input("clear-selection-button", "n_clicks"),
    Input("select-all-button", "n_clicks"),
    State("data-table", "filter_query"),
    State("data-table", "sort_by"),
    State("data-table", "data"),
    prevent_initial_call=True,
)
def bulk_selection(_clear, _select_all, filter_query, sort_by, data):
    if callback_context.triggered_id == "clear-selection-button":
        return [], []

    try:
        positions = _filtered_sorted_positions(filter_query, sort_by)
    except FilterError:
        raise PreventUpdate
    df_redu = _load_redu_sampledata()
    if 'USI' not in df_redu.columns:
        raise PreventUpdate
    usis = df_redu['USI'].iloc[positions[:MAX_SELECTION]].tolist()
    selected = set(usis)
    return usis, [i for i, usi in enumerate(_usis_on_page(data)) if usi in selected]


@dash_app.callback(
    Output("selection-count", "children"),
    Output("dashboard-button", "href"),
    Output("mn-button", "href"),
    Output("massql-button", "href"),
    Output("dashboard-button", "disabled"),
    Output("mn-button", "disabled"),
    Output("massql-button", "disabled"),
    Output("select-all-button", "children"),
    Input("selected-usis", "data"),
)
def update_selection_actions(selected_usis):
    selected_usis = selected_usis or []
    n = len(selected_usis)
    select_all_label = f"Select all matching (max {MAX_SELECTION})"

    if not n:
        message = html.Span("Tick rows in the table to send files to GNPS2.", className="text-muted")
        return message, GNPS2_DASHBOARD_URL, GNPS2_NETWORKING_URL, GNPS2_MASSQL_URL, True, True, True, select_all_label

    usis = "\n".join(selected_usis)
    hash_params = json.dumps({"usi": usis})
    dashboard_hash = json.dumps({"usi": usis, "usi2": ""})

    message = [html.Strong(f"{n:,}"), f" file{'s' if n != 1 else ''} selected"]
    if n >= MAX_SELECTION:
        message.append(html.Span(f" (limit {MAX_SELECTION})", className="text-muted"))

    return (message,
            GNPS2_DASHBOARD_URL + "#" + dashboard_hash,
            GNPS2_NETWORKING_URL + "#" + hash_params,
            GNPS2_MASSQL_URL + "#" + hash_params,
            False, False, False, select_all_label)


@dash_app.callback(
    Output("download-dataframe-csv", "data"),
    Input("download-button", "n_clicks"),
    Input("USIdownload-button", "n_clicks"),
    State("data-table", "filter_query"),
    State("data-table", "sort_by"),
    prevent_initial_call=True
)
def download_filtered_data(n_clicks, n_clicks2, filter_query, sort_by):
    if not n_clicks and not n_clicks2:
        raise PreventUpdate

    try:
        positions = _filtered_sorted_positions(filter_query, sort_by)
    except FilterError:
        raise PreventUpdate
    df_redu_filtered = _load_redu_sampledata().iloc[positions]

    if callback_context.triggered_id == 'USIdownload-button':
        if 'USI' not in df_redu_filtered.columns:
            raise PreventUpdate
        df_usis = df_redu_filtered[['USI']].rename(columns={'USI': 'usi'})
        return dcc.send_data_frame(df_usis.to_csv, "usis.csv", index=False)

    return dcc.send_data_frame(df_redu_filtered.to_csv, "filtered_dataset.csv", index=False)


if __name__ == '__main__':
    app.run_server(debug=True)
