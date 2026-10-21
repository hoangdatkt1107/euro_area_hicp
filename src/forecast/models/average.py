"""Average of the direct and bottom-up forecasts."""
NEEDS = ["direct", "bottom_up"]


def forecast(f, snap, done):
    return (done["direct"][0] + done["bottom_up"][0]) / 2, None
