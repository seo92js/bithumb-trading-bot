import pybithumb
import datetime
import time
import logging

COIN_NUM = 5
MAX_NOISE = 0.5
K = 0.5

#logger
logger = logging.getLogger("Log")
logger.setLevel(logging.DEBUG)
stream_handler = logging.StreamHandler()
file_handler = logging.FileHandler(filename = "log.txt")
logger.addHandler(stream_handler)
logger.addHandler(file_handler)

# 로그인
with open("bithumbKey.txt") as f:
    lines = f.readlines()
    apikey = lines[0].strip()
    seckey = lines[1].strip()

    bithumb = pybithumb.Bithumb(apikey, seckey)

def write_log(text):
    now = datetime.datetime.now()
    logger.info("[" + str(now.year) + "-" + str(now.month) + "-" + str(now.day) + " " + str(now.hour) + ":" + str(now.minute) + ":" + str(now.second) + "] " + text)

def get_krw():
    '''
    원화자산 가져오기
    :return: 원화
    '''
    krw = bithumb.get_balance("BTC")[2]

    return krw

def get_accounts(tickers):
    '''
    내 자산정보를 가져온다, 보유중이면 holding True
    :param tickers:
    :return: 자산, 보유여부
    '''
    try:
        accounts = {}
        holdings = {}
        for ticker in tickers:
            account = accounts[ticker] = bithumb.get_balance(ticker)[0]
            if account != 0.0:
                holdings[ticker] = True
            else:
                holdings[ticker] = False

        return accounts, holdings
    except:
        return None, None

def get_invest_cost(max_num):
    '''
    항목 별 투자금액 결정
    :param max_num: 투자 할 종목 갯수
    :return: 종몰 별 투자금액
    '''
    try:
        krw = get_krw()
        invest_cost = int(krw / max_num)

        return invest_cost
    except:
        return 0

def set_portfolio(tickers):
    '''
    듀얼노이즈 전략으로 포트폴리오 만들기,
    노이즈가 0.6 미만이고, 가장 작은 20개 종목
    :param tickers: 모든 ticker 목록
    :return: 포트폴리오
    '''
    portfolio = []
    noise_list = []

    try:
        for ticker in tickers:
            df = pybithumb.get_ohlcv(ticker)
            noise = 1 - abs(df['open'] - df['close']) / (df['high'] - df['low'])
            average_noise = noise.rolling(window=5).mean()[-2]
            noise_list.append((ticker, average_noise))

        sorted_noise_list = sorted(noise_list, key=lambda x: x[1])

        for noise in sorted_noise_list[:20]:
            if noise[1] < MAX_NOISE:
                portfolio.append(noise[0])

        return portfolio
    except:
        return None

def cal_target_price(ticker):
    '''
    ticker 금일 목표가 계산, 목표가는 변동폭(전일 고가 - 전일 저가) * K 이상
    :param ticker: 계산할 ticker
    :return: 목표가
    '''
    try:
        df = pybithumb.get_ohlcv(ticker)
        yesterday = df.iloc[-2]
        today = df.iloc[-1]
        today_open = today['open']
        yesterday_high = yesterday['high']
        yesterday_low = yesterday['low']

        target_price = today_open + (yesterday_high - yesterday_low) * K

        return target_price
    except:
        write_log("[error] cal_target_price")
        return None

def cal_target_price_all(tickers):
    '''
    지정한 ticker 목록 or 모든 ticker 목륵의 금일 목표가를 계산
    :param tickers: 지정한 ticker 목록 or 모든 ticker 목록
    :return: 목표가
    '''
    targets = {}
    for ticker in tickers:
        targets[ticker] = cal_target_price(ticker)

    return targets

def get_price(tickers):
    '''
    ticker 목록의 현재가를 받아온다
    :param tickers: 지정한 ticker 목록
    :return: 현재 가격
    '''
    try:
        all = bithumb.get_current_price("ALL")
        prices = {ticker : float(all[ticker]['closing_price']) for ticker in tickers}
        return prices
    except:
        write_log("[error] get_price")
        return None

def get_yesterday_ma5(ticker):
    '''
    ticker의 5일 이동평균을 구한다
    :param ticker: 종목
    :return: ticker의 5일 이동평균
    '''
    try:
        df = pybithumb.get_ohlcv(ticker)
        close = df['close']
        ma5 = close.rolling(window = 5).mean()

        return ma5[-2]
    except:
        write_log("[error] get_yesterday_ma5")
        return None

def get_yesterday_ma5_all(tickers):
    '''
    tickers의 5일 이동평균을 구한다
    :param tickers: 종목들
    :return: tickers의 5일 이동평균
    '''
    tickers_ma5 = {}
    for ticker in tickers:
        tickers_ma5[ticker] = get_yesterday_ma5(ticker)

    return tickers_ma5

def get_min_order(price):
    '''
    빗썸 API 최소 주문수량 기준
    금액대 별로 최소 주문수량을 가져온다.
    :param price: 금액
    :return: 최소 주문수량
    '''
    if price < 100:
        min_quantity = 10
    elif price < 1000:
        min_quantity = 1
    elif price < 10000:
        min_quantity = 0.1
    elif price < 100000:
        min_quantity = 0.01
    elif price < 1000000:
        min_quantity = 0.001
    else:
        min_quantity = 0.0001

    return min_quantity


def try_buy(tickers, tickers_current_price, tickers_target, tickers_ma5, invest_cost, holdings):
    '''
    매수조건 충족 시 매수 진행
    :param tickers: 종목들
    :param tickers_current_price: 종목들의 현재가
    :param tickers_target: 종목들의 목표가
    :parem tickers_ma5: 종목들의 5일 이동평균
    :param invest_cost: 종목 별 투자금액
    :param holdings: 종목 보유 여부
    '''
    try:
        for ticker in tickers:
            current_price = tickers_current_price[ticker]
            target = tickers_target[ticker]
            ma5 = tickers_ma5[ticker]
            min_order = get_min_order(current_price)
            if holdings[ticker] == False:                                                       #보유중이 아니고
                if current_price > target and current_price > ma5:                              #가격이 목표가 이상이고, 5일 이동평균 이상일 때
                    orderbook = pybithumb.get_orderbook(ticker)
                    sell_price = orderbook['asks'][0]['price']
                    unit = invest_cost / float(sell_price)

                    if unit > min_order and (unit * sell_price) > 1000:                         #최소주문수량 이상이고, 1000원 이상일 때
                        result = bithumb.buy_market_order(ticker, unit)

                        if result is None:
                            # 재시도?
                            pass
                        else:
                            holdings[ticker] = True
                            write_log("[buy] " + ticker + " : " + str(unit))
                    time.sleep(1)

    except:
        write_log("[error] try_buy")
        pass

def print_status(now, tickers, prices, targets, ma5, holdings):
    '''
    실시간 상태출력
    :param now: 현재시간
    :param tickers: 종목
    :param prices: 현재가
    :param targets: 목표가
    :param ma5: 이동평균
    :param holdings: 보유상태
    :return:
    '''
    try:
        print("-" * 60)
        print(now)
        print("원화잔고 : " + str(get_krw()) + "\n")

        for ticker in tickers:
            price = prices[ticker]
            target = targets[ticker]
            ma = ma5[ticker]

            if price > target and price > ma:
                market = "\033[31m상승장"
            else:
                market = "\033[34m하락장"

            if holdings[ticker] is False:
                holding = "\033[0m미보유"
            else:
                holding = "\033[32m보유"

            print("\033[0m[{0}] 현재가 : {1:>8.0f}, 목표가 : {2:>8.0f} - {3} - {4}".format(ticker, price, target, market, holding))
    except:
        write_log("[error] print_status")
        pass

def try_sell(tickers, tickers_current_price):
    '''
    시초가에 전량 매도
    :param tickers: 종목
    '''
    try:
        for ticker in tickers:
            unit = bithumb.get_balance(ticker)[0]
            current_price = tickers_current_price[ticker]
            min_order = get_min_order(current_price)

            if unit >= min_order:
                result = bithumb.sell_market_order(ticker, unit)
                time.sleep(1)
                if result is None:
                    retry_sell(ticker, unit, 10)
                    pass
                else:
                    write_log("[sell] " + ticker + " : " + str(unit))
    except:
        write_log("[error] try_sell")
        pass

def retry_sell(ticker, unit, count):
    '''
    판매 재시도
    :param ticker: 종목
    :param unit: 판매 갯수
    :param count: 반봇 횟수
    '''
    try:
        result = None
        while result is None and count > 0:
            result = bithumb.sell_market_order(ticker, unit)
            time.sleep(1)

            write_log("[retry sell] " + ticker + " : " + str(unit))
            count = count - 1
    except:
        write_log("[error] retry_buy")
        pass

#시작
tickers = bithumb.get_tickers()
portfolio = set_portfolio(tickers)                                                                          #포트폴리오 설정
ignore_tickers = ["SGB"]                                                                                    #제외종목

#프로그램 실행시 현재시간조회
now = datetime.datetime.now()
mid = datetime.datetime(now.year, now.month, now.day) + datetime.timedelta(1)

tickers_target = cal_target_price_all(portfolio)                                                            #목표가 설정
tickers_ma5 = get_yesterday_ma5_all(portfolio)                                                              #5일 이동평균 계산
invest_cost = get_invest_cost(COIN_NUM)                                                                     #투자비율 결정

holdings = {ticker : False for ticker in tickers}

while True:
    now = datetime.datetime.now()

    if mid < now < mid + datetime.timedelta(seconds = 10):                                                  #다음날 넘어가면
        mid = datetime.datetime(now.year, now.month, now.day) + datetime.timedelta(1)
        try_sell(tickers, tickers_current_price)                                                                                   #전량 매도
        holdings = {ticker: False for ticker in tickers}

        portfolio = set_portfolio(tickers)                                                                  #포트폴리오 재 설정
        tickers_target = cal_target_price_all(portfolio)                                                        #목표가 재 설정
        tickers_ma5 = get_yesterday_ma5_all(portfolio)                                                      #5일 이동평균 재 계산
        invest_cost = get_invest_cost(COIN_NUM)                                                             #투자비율 재 결정

        time.sleep(10)

    tickers_current_price = get_price(tickers)                                                            #현재가 받아오기

    print_status(now, portfolio, tickers_current_price, tickers_target, tickers_ma5, holdings)              #상태 출력

    try_buy(portfolio, tickers_current_price, tickers_target, tickers_ma5, invest_cost, holdings)           #매수조건 따져서 매수시도

    time.sleep(1)


