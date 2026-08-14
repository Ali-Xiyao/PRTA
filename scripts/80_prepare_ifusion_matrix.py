from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "prepare_ifusion_matrix_main",
            module_name="prta_cxr.ifusion_matrix",
        )
    )
