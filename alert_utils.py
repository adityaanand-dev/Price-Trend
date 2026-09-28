def price_crosses_threshold(df, column='Close', threshold=0.0, direction='above'):
    """Return True if the latest price crosses *threshold* in the specified *direction*.
    *direction*: 'above' or 'below'.
    """
    if df.empty:
        return False
    latest = df[column].iloc[-1]
    if direction == 'above':
        return latest > threshold
    return latest < threshold
