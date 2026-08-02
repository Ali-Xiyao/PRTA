from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch("seal_split_surfaces_main", module_name="prta_cxr.cli_protocol")
    )
