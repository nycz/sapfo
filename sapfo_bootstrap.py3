if __name__ == '__main__':
    try:
        import sapfo
        sapfo.main()
    except:
        from libsyntyche import common
        common.print_traceback()
        input()
