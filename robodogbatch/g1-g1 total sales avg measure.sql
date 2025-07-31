```sql
CREATE FUNCTION dbo.GetTotalSales()
RETURNS DECIMAL(18, 2)
AS
BEGIN
    DECLARE @TotalSales DECIMAL(18, 2);
    SELECT @TotalSales = AVG(SalesAmount)
    FROM FactTable;
    RETURN @TotalSales;
END;
```