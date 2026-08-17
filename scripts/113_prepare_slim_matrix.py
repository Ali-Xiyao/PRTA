from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch("prepare_slim_matrix_main", module_name="prta_cxr.slim_matrix")
    )
