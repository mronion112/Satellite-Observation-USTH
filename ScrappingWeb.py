"""Notes from the original scraper draft:

Đầu tiên là lấy tất cả các thẻ section class = "reception" sau đó với mỗi thẻ ấy lấy div class = "reception-time" lấy thẻ <div><strong> để lấy thời gian của nó. Và sau đó với mỗi thẻ <a> class = "data-card" lấy 4 cái link href trong đấy bao gồm CADU, TElemetry JSON, DAtaset JSON, Product CBOR
"""

from main import main


if __name__ == "__main__":
    raise SystemExit(main())
