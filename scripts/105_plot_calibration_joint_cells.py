from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch("aggregate_figures_main", module_name="prta_cxr.aggregate_figures")
    )
