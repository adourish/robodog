To enable mocking of the `FactTable` data when calculating the total sales, you can modify the `GetTotalSales` function to accept the sales data as a table-valued parameter. This approach allows you to pass in different datasets, including mock data, for testing purposes.

Here's a step-by-step guide to achieve this:

### 1. Define a Table Type

First, create a user-defined table type that mirrors the structure of your `FactTable`. This type will be used to pass the table data to the function.

```sql
-- Create a table type for FactTable
CREATE TYPE dbo.FactTableType AS TABLE
(
    SalesAmount DECIMAL(18, 2)
    -- Add other columns from FactTable if needed
);
```

### 2. Modify the Function to Accept the Table Type

Next, update the `GetTotalSales` function to accept a parameter of the newly created table type. The function will compute the sum of `SalesAmount` from the provided table.

```sql
-- Modify the function to accept a table-valued parameter
CREATE FUNCTION dbo.GetTotalSales(@FactData dbo.FactTableType READONLY)
RETURNS DECIMAL(18, 2)
AS
BEGIN
    DECLARE @TotalSales DECIMAL(18, 2);

    SELECT @TotalSales = SUM(SalesAmount)
    FROM @FactData;

    RETURN @TotalSales;
END;
```

**Explanation:**

- The function `GetTotalSales` now takes a parameter `@FactData` of type `dbo.FactTableType`.
- The `READONLY` keyword is required for table-valued parameters.
- The function computes the total sales by summing the `SalesAmount` from the provided table.

### 3. Mocking Data and Testing the Function

You can now create mock data by declaring a variable of the table type and populating it with test values. Then, pass this mock data to the `GetTotalSales` function.

```sql
-- Declare a variable of the table type
DECLARE @MockFactData dbo.FactTableType;

-- Insert mock data into the table variable
INSERT INTO @MockFactData (SalesAmount)
VALUES
    (100.00),
    (250.50),
    (399.99),
    (150.25);

-- Call the function with the mock data
SELECT dbo.GetTotalSales(@MockFactData) AS TotalSales;
```

**Expected Output:**

```
TotalSales
-----------
900.74
```

**Explanation:**

- A table variable `@MockFactData` of type `dbo.FactTableType` is declared.
- Mock sales amounts are inserted into `@MockFactData`.
- The `GetTotalSales` function is called with `@MockFactData` as the input, and the total sales are returned.

### 4. Using Actual `FactTable` Data

When you want to use the function with actual data from `FactTable`, you can pass the data by selecting it into a table variable and then calling the function.

```sql
-- Declare a variable of the table type
DECLARE @ActualFactData dbo.FactTableType;

-- Insert actual data from FactTable into the table variable
INSERT INTO @ActualFactData (SalesAmount)
SELECT SalesAmount FROM FactTable;

-- Call the function with the actual data
SELECT dbo.GetTotalSales(@ActualFactData) AS TotalSales;
```

### 5. Automating with Stored Procedures (Optional)

If you frequently need to switch between mock and actual data, consider creating stored procedures that encapsulate these operations for easier testing and deployment.

---

By restructuring the `GetTotalSales` function to accept a table-valued parameter, you gain the flexibility to pass in any dataset, including mock data, facilitating easier testing and development.