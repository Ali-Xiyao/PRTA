from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "prepare_server_dev_search_main",
            module_name="prta_cxr.server_dev_search",
        )
    )
