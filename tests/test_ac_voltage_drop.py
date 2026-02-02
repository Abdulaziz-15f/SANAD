from core.parsers.ac_cable_sizing import parse_ac_cable_sizing_excel
from core.checks.voltage_drop import check_voltage_drop

if __name__ == "__main__":
    path = "/Users/mohammedalharbi/Documents/HACKATHONS/UTURETHON/SANAD/tests/AC Cable_Sizing_Equations.xlsx"
    inv_runs, comb_runs = parse_ac_cable_sizing_excel(path)

    print("Inverter runs:", len(inv_runs))
    print("Combiner runs:", len(comb_runs))

    issues = check_voltage_drop(inv_runs, comb_runs, inverter_vd_limit_pct=3.0, combiner_vd_limit_pct=1.5)
    print("Issues:", len(issues))

    # Print first 3 issues (if any)
    for i in issues[:3]:
        print(i.severity, i.title, "|", i.description)
