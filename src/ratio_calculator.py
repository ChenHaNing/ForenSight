from typing import Any, Dict


class FinancialRatioCalculator:
    def __init__(self, financial_data: Dict[str, Any]) -> None:
        self.income_statement = financial_data.get("income_statement", {}) or {}
        self.balance_sheet = financial_data.get("balance_sheet", {}) or {}
        self.market_data = financial_data.get("market_data", {}) or {}

    @staticmethod
    def _safe_divide(numerator: float, denominator: float) -> float:
        if denominator == 0:
            return 0.0
        return numerator / denominator

    def calculate_profitability_ratios(self) -> Dict[str, float]:
        net_income = self.income_statement.get("net_income", 0)
        equity = self.balance_sheet.get("shareholders_equity", 0)
        assets = self.balance_sheet.get("total_assets", 0)
        revenue = self.income_statement.get("revenue", 0)
        cogs = self.income_statement.get("cost_of_goods_sold", 0)
        operating_income = self.income_statement.get("operating_income", 0)
        return {
            "roe": self._safe_divide(net_income, equity),
            "roa": self._safe_divide(net_income, assets),
            "gross_margin": self._safe_divide(revenue - cogs, revenue),
            "operating_margin": self._safe_divide(operating_income, revenue),
            "net_margin": self._safe_divide(net_income, revenue),
        }

    def calculate_liquidity_ratios(self) -> Dict[str, float]:
        current_assets = self.balance_sheet.get("current_assets", 0)
        current_liabilities = self.balance_sheet.get("current_liabilities", 0)
        inventory = self.balance_sheet.get("inventory", 0)
        cash = self.balance_sheet.get("cash_and_equivalents", 0)
        return {
            "current_ratio": self._safe_divide(current_assets, current_liabilities),
            "quick_ratio": self._safe_divide(current_assets - inventory, current_liabilities),
            "cash_ratio": self._safe_divide(cash, current_liabilities),
        }

    def calculate_leverage_ratios(self) -> Dict[str, float]:
        debt = self.balance_sheet.get("total_debt", 0)
        equity = self.balance_sheet.get("shareholders_equity", 0)
        ebit = self.income_statement.get("ebit", 0)
        interest = self.income_statement.get("interest_expense", 0)
        operating_income = self.income_statement.get("operating_income", 0)
        current_portion = self.balance_sheet.get("current_portion_long_term_debt", 0)
        return {
            "debt_to_equity": self._safe_divide(debt, equity),
            "interest_coverage": self._safe_divide(ebit, interest),
            "debt_service_coverage": self._safe_divide(
                operating_income, interest + current_portion
            ),
        }

    def calculate_efficiency_ratios(self) -> Dict[str, float]:
        revenue = self.income_statement.get("revenue", 0)
        assets = self.balance_sheet.get("total_assets", 0)
        cogs = self.income_statement.get("cost_of_goods_sold", 0)
        inventory = self.balance_sheet.get("inventory", 0)
        receivables = self.balance_sheet.get("accounts_receivable", 0)
        receivables_turnover = self._safe_divide(revenue, receivables)
        return {
            "asset_turnover": self._safe_divide(revenue, assets),
            "inventory_turnover": self._safe_divide(cogs, inventory),
            "receivables_turnover": receivables_turnover,
            "days_sales_outstanding": self._safe_divide(365, receivables_turnover),
        }

    def calculate_valuation_ratios(self) -> Dict[str, float]:
        share_price = self.market_data.get("share_price", 0)
        shares = self.market_data.get("shares_outstanding", 0)
        net_income = self.income_statement.get("net_income", 0)
        revenue = self.income_statement.get("revenue", 0)
        equity = self.balance_sheet.get("shareholders_equity", 0)
        debt = self.balance_sheet.get("total_debt", 0)
        cash = self.balance_sheet.get("cash_and_equivalents", 0)
        ebitda = self.income_statement.get("ebitda", 0)
        growth = self.market_data.get("earnings_growth_rate", 0)

        market_cap = share_price * shares
        eps = self._safe_divide(net_income, shares)
        book_value_per_share = self._safe_divide(equity, shares)
        pe_ratio = self._safe_divide(share_price, eps)
        peg_ratio = self._safe_divide(pe_ratio, growth * 100) if growth > 0 else 0.0

        return {
            "eps": eps,
            "pe_ratio": pe_ratio,
            "book_value_per_share": book_value_per_share,
            "pb_ratio": self._safe_divide(share_price, book_value_per_share),
            "ps_ratio": self._safe_divide(market_cap, revenue),
            "ev_to_ebitda": self._safe_divide(market_cap + debt - cash, ebitda),
            "peg_ratio": peg_ratio,
        }

    def calculate_all_ratios(self) -> Dict[str, Any]:
        return {
            "profitability": self.calculate_profitability_ratios(),
            "liquidity": self.calculate_liquidity_ratios(),
            "leverage": self.calculate_leverage_ratios(),
            "efficiency": self.calculate_efficiency_ratios(),
            "valuation": self.calculate_valuation_ratios(),
        }
