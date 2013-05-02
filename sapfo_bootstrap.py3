if __name__ == '__main__':
    try:
        import sapfo
        sapfo.main()
    except Exception: # and not SystemExit
        from libsyntyche import common
        common.print_traceback()
        input()
