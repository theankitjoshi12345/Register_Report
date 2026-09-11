# ANY AGENT IS NOT PERMITTED TO DO ANY CHANGE IN THIS FILE

There needs to be option for both day close and shift close depending on what the user want to perform. There always needs to be a day close.

## Lottery  

There are 20 different scratchoff each one assigned a number.
Number 1 is $20 from 000 to 024
Number [2:3] is $10 from 000 to 024
Number [4:7] is $5 from 000 to 049
Number [8-10] is $3 from 000 to 074
Number [11-15] is $2 from 000 to 124
Number [16-20] is $1 from 000 to 249

User cannot enter the invalid number. They can leave it empty. 
This will result in giving us the actual total sctarch off sales. 

The lottery terminal will provide two important number, which is also entered by the user. One is actual intant ticket sales and another is actual payout.
There are two POS registers: one can be reffered as gas register and another can be reffered as bodega ai register used in this store.
Both of them will provide two sales/payout values:
Lottery Sales
Lottery Payout

The backend will add both sales/payout values across both register and compare it against the actual number. 

Actual scratch off sales + Actual Lottery sales == Combined Lottery sales across POS
Actual payout sales == Combine POS payout sales

There also need to be a button which users can click if they want to add a new roll of scratch off tickets before the day ends. 

Our backend should be able to handle this based on just the number provided by the user. 


## PhoneCard

Same like lottery, there is one phone card generating machine, which will provide what is the actual phone card sales for the day.

This actual sales needs to be compared against the saled performed by the both the registers. 

The owner will enter the sales from both the POS registers.
The backend will compare this number against the actual sales.


## Tickets [This is only for gas register. This means the fake sales, which people owes to the store.]

This is a new feature unlike other stores. This business let their regular customers make a ticket and pay it next day if they are known. 

At the end of the day, the owner will enter the total ticket make that day on gas register. This feature will not be there for bodega ai register. 
Please allow user to input optional multiple amounts.
There needs to be optional description box for the tickets where user can add any data if they want.
At the end of the day/shift, this amount will be used.


## Vender Payout [This is only for gas register]

This will perform exactly like tickets. Please also provide the optional description box. 
At the end of the day, this amount will be used. 
Please allow user to input optional multiple amounts.

## Card Sales [ This is only for gas register]

The owner will put in the total cash sales for gas register. It has a seperate card machiche which it uses to use card which is not connected to POS. So it works independently and we put that sale as cash for the POS.

At the end of the day/shift, user has to put in the total card sales for gas register. 
For front end, please provide to enter the net amount without including fees. 

The backend will use this amount at the end of the day/shift. 


## Safe Drop [This is only for gas register]
This is the total cash amount dropped by in the locked safe, similar to in store locker. 
Please allow user to input optional multiple amounts. 

## Gas [This is only for bodega AI register]
This is the total amount of gas sold by bodega Ai register.

This POS doesn't have access to the pump which means the money is collected in this register but sold by gas register. 

This is fake sale for gas register. The backend will use this amount at the end of day/shift.


## Net Difference [This is only for Bodega AI register.]
At the end of the day, this is the difference amount in the bodega Ai register. It could be either + or -. 
User should be able to input either positive or negative amount

## What the owner will input everytime when closing day/shift?
All of these needs to be in steps. 

Independent Things: 
Phone Card Sales

Lottery Terminal:
Lottery Sales
Lottery Payout

Scratch Off:
1
...
20
// 20 different ending numbers.  Every number should be followed by a checkbox if any new roll was added today. That needs to send a confirmation before adding a checkfor for _ scratch number.

Bodega AI:
Net Difference
Lottery Sales
Lottery Payout
Phone Card
Gas

Gas Register:
Total Cash Sales
Safe Drop
Tickets
Lottery Sales
Lottery Payout

## Clarifications (2026-09-10)

- Authentication and authorization are intentionally deferred until the rest of
    the product is complete.
- Scratch-off counters accept either a valid whole-number ticket counter or
    empty/null. An empty ending counter means all tickets remaining in that roll
    were sold.
- Scratch-off sales use the ticket price and the clarified roll formula:
    `(ending - starting) + (new roll counter - 1) * (ticket ending - starting + 1)
    + (ending - last night number + 1)`, then multiplied by ticket price.
- The new-roll value is a counter per scratch-off slot, not only a checkbox.
- Bodega AI net difference is required and may be positive or negative, with
    up to two decimal places.
- Reports must be editable after saving.
- Report data should use normalized, queryable records for line items and
    scratch-off rolls rather than relying only on JSON blobs.
Vender Payout
Card Machine without including fee

## How backend will function

For phone card, it will check the difference as mentioned above.

For Lottery sales and payout, it will check the difference as mentioned above.

For bodega AI, it will just display the Net difference amount.

For gas register, it has to to do the math, which is
    Total cash sales - gas (from bodega AI) - safe drop - tickets - vender payout -         cardmachine without including fee

    This is provide the net difference for the gas register which could be both positive and negative. 

The backend should provide all of these things in a table to the user. Like
    
    Bodega Ai [Net Difference: ]
    Gas Register [Net Difference: ]

    PHone card [Expected: , Actual: ]
    Lottey sales [Expectee: , Actual: ]
    Lottery payout [Expectee: , Actual: ]

    Then display all the information user had input.


## UI

We shoudld be able to access reports/shifts from any day as well.









