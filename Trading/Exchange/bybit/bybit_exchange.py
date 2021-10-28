#  Drakkar-Software OctoBot-Tentacles
#  Copyright (c) Drakkar-Software, All rights reserved.
#
#  This library is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 3.0 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library.
import octobot_trading.enums as trading_enums
import octobot_trading.exchanges as exchanges
import octobot_commons.constants as commons_constants
import octobot_trading.constants as trading_constants
import octobot_trading.errors


class Bybit(exchanges.SpotCCXTExchange, exchanges.FutureCCXTExchange):
    DESCRIPTION = ""

    BUY_STR = "Buy"
    SELL_STR = "Sell"

    MARK_PRICE_IN_TICKER = True
    FUNDING_IN_TICKER = True

    # Spot keys
    BYBIT_KLINE_TIMESTAMP = "open_time"

    BYBIT_SYMBOL = "symbol"

    # Position
    BYBIT_SIZE = "size"
    BYBIT_VALUE = "position_value"
    BYBIT_MARGIN = "position_margin"
    BYBIT_STATUS = "position_status"
    BYBIT_LIQUIDATION_PRICE = "liq_price"
    BYBIT_TIMESTAMP = "created_at"
    BYBIT_IS_ISOLATED = "is_isolated"

    # Funding
    BYBIT_FUNDING_TIMESTAMP = "funding_rate_timestamp"
    BYBIT_DEFAULT_FUNDING_TIME = 8 * commons_constants.HOURS_TO_SECONDS

    @classmethod
    def get_name(cls) -> str:
        return 'bybit'

    @classmethod
    def is_supporting_exchange(cls, exchange_candidate_name) -> bool:
        return cls.get_name() == exchange_candidate_name

    async def get_symbol_prices(self, symbol, time_frame, limit: int = 200, **kwargs: dict):
        # Bybit return an error if there is no limit or since parameter
        try:
            return await self.connector.client.fetch_ohlcv(symbol, time_frame.value, limit=limit, params=kwargs)
        except Exception as e:
            raise octobot_trading.errors.FailedRequest(f"Failed to get_symbol_prices {e}")

    async def initialize_impl(self):
        await super().initialize_impl()

        # temporary patch defaultMarketType to linear
        self.connector.client.options['defaultType'] = 'linear'

    async def get_open_positions(self) -> list:
        return self.parse_positions(await self.connector.client.fetch_positions())

    async def get_symbol_leverage(self, symbol: str):
        # TODO returned error during implementation tests
        user_leverage = await self.connector.client.user_get_leverage()
        return user_leverage["result"][symbol] if symbol in user_leverage["result"] else None

    async def get_contract_type(self, symbol: str):
        import ccxt.async_support.binance
        market_types = self.connector.client.safe_value(self.connector.client, 'marketTypes', {})
        symbol_market_type = market_types.get(self.get_exchange_pair(symbol), None)
        pass

    # async def get_kline_price(self, symbol, time_frame):
    #     try:
    #         await self.connector.client.public_get_kline_list(
    #             {
    #                 "symbol": self.get_exchange_pair(symbol),
    #                 "interval": "",
    #                 "from": "",
    #                 "limit": 1
    #              })
    #     except BaseError as e:
    #         self.logger.error(f"Failed to get_kline_price {e}")
    #         return None

    def parse_positions(self, positions) -> list:
        """
        CCXT is returning the position dict as {'data': {position data dict}}
        """
        return [self.parse_position(position.get('data')) for position in positions]

    def parse_position(self, position_dict) -> dict:
        try:
            return super().parse_position(
                {
                    'symbol': self.get_pair_from_exchange(
                        position_dict[trading_enums.ExchangeConstantsPositionColumns.SYMBOL.value]),
                    'timestamp': self.parse_timestamp(position_dict, self.BYBIT_TIMESTAMP),
                    'datetime': self.connector.client.iso8601(
                        self.parse_timestamp(position_dict, self.BYBIT_TIMESTAMP)),
                    'initialMargin': initialMargin,
                    'initialMarginPercentage': self.parse_number(initialMarginPercentageString),
                    'maintenanceMargin': maintenanceMargin,
                    'maintenanceMarginPercentage': maintenanceMarginPercentage,
                    'entryPrice': self.connector.client.parse_number(
                        position_dict, trading_enums.ExchangeConstantsPositionColumns.ENTRY_PRICE.value, 0),
                    'notional': self.connector.client.parse_number(
                        position_dict, self.BYBIT_VALUE, 0),
                    'leverage': self.connector.client.parse_number(
                        position_dict, trading_enums.ExchangeConstantsPositionColumns.LEVERAGE.value, 0),
                    'unrealizedPnl': self.connector.client.parse_number(
                        position_dict, trading_enums.ExchangeConstantsPositionColumns.UNREALISED_PNL.value, 0),
                    'contracts': self.connector.client.parse_number(position_dict, self.BYBIT_SIZE, 0),
                    'contractSize': self.connector.client.parse_number(position_dict, self.BYBIT_SIZE, 0),
                    'marginRatio': None,
                    'liquidationPrice': self.connector.client.parse_number(
                        position_dict, self.BYBIT_LIQUIDATION_PRICE, 0),
                    'markPrice': self.connector.client.parse_number(
                        position_dict, trading_enums.ExchangeConstantsPositionColumns.MARK_PRICE.value, 0),
                    'collateral': self.connector.client.parse_number(
                        position_dict, trading_enums.ExchangeConstantsPositionColumns.COLLATERAL.value, 0),
                    'marginType': self._parse_position_margin_type(position_dict.get(self.BYBIT_IS_ISOLATED, True)),
                    'side': self.parse_position_side(self.connector.client.safe_string(
                        position_dict,
                        trading_enums.ExchangeConstantsPositionColumns.SIDE.value,
                        default_value=trading_enums.PositionSide.UNKNOWN.value)),
                    'percentage': None,
                })
        except KeyError as e:
            self.logger.error(f"Fail to parse position dict ({e})")
        return position_dict

    def parse_funding(self, funding_dict, from_ticker=False):
        if from_ticker and trading_constants.CCXT_INFO in funding_dict:
            funding_dict, old_funding_dict = funding_dict[trading_constants.CCXT_INFO], funding_dict

        try:
            """
            Bybit last funding time is not provided
            To obtain the last_funding_time : 
            => timestamp(next_funding_time) - timestamp(BYBIT_DEFAULT_FUNDING_TIME)
            """
            funding_next_timestamp = self.parse_timestamp(
                funding_dict, trading_enums.ExchangeConstantsFundingColumns.NEXT_FUNDING_TIME.value)
            funding_dict.update({
                trading_enums.ExchangeConstantsFundingColumns.LAST_FUNDING_TIME.value:
                    funding_next_timestamp - self.BYBIT_DEFAULT_FUNDING_TIME,
                trading_enums.ExchangeConstantsFundingColumns.FUNDING_RATE.value: self.connector.client.safe_float(
                    funding_dict, trading_enums.ExchangeConstantsFundingColumns.FUNDING_RATE.value),
                trading_enums.ExchangeConstantsFundingColumns.NEXT_FUNDING_TIME.value: funding_next_timestamp
            })
        except KeyError as e:
            self.logger.error(f"Fail to parse funding dict ({e})")
        return funding_dict

    def parse_mark_price(self, mark_price_dict, from_ticker=False) -> dict:
        if from_ticker and trading_constants.CCXT_INFO in mark_price_dict:
            mark_price_dict = mark_price_dict[trading_constants.CCXT_INFO]

        try:
            mark_price_dict = {
                trading_enums.ExchangeConstantsMarkPriceColumns.MARK_PRICE.value:
                    self.connector.client.safe_float(mark_price_dict,
                                                     trading_enums.ExchangeConstantsMarkPriceColumns.MARK_PRICE.value,
                                                     0)
            }
        except KeyError as e:
            self.logger.error(f"Fail to parse mark price dict ({e})")

        return mark_price_dict

    def parse_position_status(self, status):
        statuses = {
            'Normal': 'open',
            'Liq': 'liquidating',
            'Adl': 'auto_deleveraging',
        }
        return trading_enums.PositionStatus(self.connector.client.safe_string(statuses, status, status))

    def _parse_position_margin_type(self, position_is_isolated):
        return trading_enums.TraderPositionType.ISOLATED.value \
            if position_is_isolated else trading_enums.TraderPositionType.CROSS.value
