"""Offline Wyscout adapter. The blocked Figshare source is never requested here."""

import pandas as pd


def convert_events(events: list[dict], home_team_id: int) -> pd.DataFrame:
    """Use the pinned socceraction converter on owner-provided Pappalardo files.

    Source X/Y percentages are acting-team attacking-relative. Socceraction makes
    home attack +x across periods; original native event IDs survive conversion.
    The package's loader normalization is reused without instantiating its loader
    (which can implicitly download when its directory is empty).
    """
    from socceraction.data.wyscout.loader import _convert_events
    from socceraction.spadl import add_names
    from socceraction.spadl.wyscout import convert_to_actions

    normalized = _convert_events(pd.DataFrame(events))
    actions = add_names(convert_to_actions(normalized, home_team_id))
    actions["home_team_id"] = home_team_id
    return actions
