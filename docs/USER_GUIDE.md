# User guide

SmartPOS AI runs in a web browser on a computer, tablet or phone. What you see
depends on your role:

| Role | Typical person | Main screens |
| --- | --- | --- |
| Cashier | Front counter, waiting staff | POS, Orders, Tables, Kitchen Display (view), Customers |
| Kitchen | Cooks | Kitchen Display |
| Manager | Owner or shift manager | Everything in the restaurant, including stock, purchasing, analytics, forecasting, the AI assistant, staff and settings |
| Administrator | Platform operator | Everything, in every restaurant, plus Administration |

The account menu (top right) switches the language between English and ไทย
(Thai covers navigation, page titles and the main POS labels; other screens
stay in English for now) and the theme between light, dark and system. It
also lets you change your password and sign out. Receipts always print in
both Thai and English. Managers and administrators with several restaurants
switch between them with the restaurant button at the top left; analytics and
reports always show the restaurant selected there.

### Finding your way around

* **Search or jump to…** (`Ctrl+K`, or `⌘K` on a Mac) opens a command palette:
  type part of a page name ("purch", "kitchen") and press Enter. It also offers
  quick actions such as *New sale*.
* The **sidebar** can be collapsed to icons with the button at its bottom; the
  choice is remembered in this browser. On phones it opens from the ☰ button.
* **Live** in the top bar means this screen receives changes as they happen:
  new orders, stock movements and table changes from other devices appear
  without reloading. *Connecting* or *Offline* means the connection dropped;
  the screen catches up by itself when it returns.
* The **bell** collects notifications for your role: an ingredient running low
  or out, a delivery received, new reorder suggestions. Opening it marks them
  as read. Urgent ones also pop up as a message.

## Signing in

Enter your email and password, then **Sign in**. Before signing in you can
switch the page to ไทย or to the dark theme (top right).

* **Show password** (the eye icon) reveals what you typed, and a warning
  appears when Caps Lock is on.
* **Keep me signed in** is on by default. Untick it on a shared till: the
  session then ends when the browser is closed.
* A wrong email or password says so, keeps your email and puts the cursor
  back in the password field. After 10 failed attempts on one account,
  sign-in pauses for a few minutes and the page counts down until you can try again.
* **Forgot password?** (next to the password label) sends a reset link when
  email is set up; the link works once, for 30 minutes. Otherwise ask a
  manager to set a new password for you. The reset page shows the password
  rules as you type.
* If your session ended, you signed out, or you just changed your password,
  the sign-in page says so. If you are still signed in, it shows your account
  with **Continue** and **Use another account**.

On a public demo installation the sign-in page also shows **Try the live
demo** with *Manager*, *Cashier* and *Kitchen* buttons, which sign you in to
the demo restaurant without a password.

## Dashboard

The dashboard shows what your role may see, and updates by itself:

* **KPI tiles:** today's net sales, orders and average order value, compared
  with the same time yesterday, with a 14-day trend line (hover it for each
  day). Managers also see **Needs attention**: ingredients at risk and reorder
  suggestions waiting.
* **Sales, last 14 days** and **Today by hour**, each with a **Table** view.
* **Stock at risk:** ingredients that run out before (or soon after) a
  delivery ordered now would arrive, with the days left and the lead time.
* **Smart insights:** short findings with the numbers behind them: how sales
  compare with yesterday, what will run out, how long the oldest kitchen ticket
  has waited, whether the forecast is out of date, this week's best seller,
  the usual peak hour for today's weekday, and menu items that have not sold
  for two weeks. Each links to the page where you can act on it.
* **Kitchen now**, **Recent orders** and **Forecast for tomorrow**.

## Selling at the POS (cashier)

1. Open **POS**. Press `/` to jump to product search, or filter by category.
2. Tap a product. If it has options (size, spice level, extras), choose them
   in the dialog; required choices are marked. Add a kitchen note such as "no
   peanuts" if needed.
3. Choose **Dine-in** (pick a table) or **Takeaway**. Optionally attach a
   customer by name or phone, or create one with the **+** button.
4. Under the cart, **suggestions** appear as chips with a reason, for example
   "In 75% of orders with Green Curry Chicken", or the selected customer's
   usual items. Tap one to add it. Products already in the cart show a count
   badge. On a phone, the **Review order** bar at the bottom jumps to the cart.
5. Check the totals on the right. They come from the server and include VAT
   and any service charge. Apply a preset discount if you are allowed to;
   larger discounts need a manager.
6. Finish with one of:
   * **Save draft:** keep the order open without sending it to the kitchen.
   * **Send to kitchen:** confirm the order (stock is deducted) and pay later.
   * **Confirm & pay** (`Ctrl+Enter`): confirm and take payment straight away.
7. In the payment dialog, choose the method. For cash, enter the amount handed
   over and the change is shown. Card and QR payments are **recorded only**:
   confirm them on your card terminal or banking app first. Every receipt says
   payments were recorded by staff.
   If you close the payment dialog without paying, the order stays confirmed
   (the kitchen already has it) and a message links to it so you can take
   payment later from **Orders**.
8. **Print receipt** opens an 80 mm receipt in a new tab.

When the kitchen marks an order ready, cashiers get a message with a link to it.

If a confirmation fails with "Not enough stock", an ingredient has run out.
Tell a manager, who can record a delivery or a stock count.

### Tables

**Tables** shows every table's status: available, occupied, reserved or
cleaning. **Start order** opens the POS for that table, and **Add items** edits
the open order while it is unpaid. When the guests have paid and left, use
**Close table** (it moves to *cleaning*), then **Mark cleaned** to make it available. Available tables can also be reserved.

### Orders, cancellations and refunds

**Orders** lists orders by date, status, payment and type, with search. Open an
order to move it along, take a payment or reprint the receipt.

* Cashiers can cancel **drafts**. Managers can cancel confirmed orders with a
  reason, and choose whether the ingredients go back into stock.
* Refunds are manager-only. They need a reason and can be partial.

## Kitchen display (kitchen)

Tickets appear in **New**, **Preparing** and **Ready** columns the moment an
order is sent; a ticket that just arrived is highlighted briefly. Each ticket shows the table or "Takeaway", items, options, notes and
the minutes since it was sent. Borders turn orange after 15 minutes and red
after 25. Tap **Start preparing**, **Mark ready**, then **Mark completed**.
Prices are never shown on the kitchen screen.

## Customers and loyalty

**Customers** stores name, phone, email and notes. Cashiers see masked phone
numbers. With loyalty enabled, customers earn 1 point per configured amount
spent on paid orders, and can redeem points at the POS ("Redeem points"). Points
are reversed when an order is cancelled or refunded. Managers can adjust points
with a reason, and can **anonymise** a customer who asks to be forgotten: the
personal details are erased, but the sales history stays.

## Menu and recipes (manager)

* **Menu → Products:** name, category, price, SKU, image URL, availability and
  option groups. A product that has been sold is archived instead of deleted.
* **Menu → Modifiers:** option groups (choose one, or choose several with
  limits). Options can change the price and use an ingredient, for example
  "Extra egg" uses 1 egg.
* **Recipes:** list the ingredients and quantities for one serving, in any unit
  (`g`, `kg`, `ml`, `l`, `piece` or a pack such as "tray"), plus a waste
  percentage. Saving creates a new version; past orders keep the version they
  used. The estimated cost per serving and the gross margin are shown.

## Inventory (manager)

* **Inventory → Ingredients:** current stock, how long it **lasts** (days of
  cover at the expected daily use, from the forecast or the last 14 days of
  sales), reorder level, safety stock, average cost and supplier. A red dot
  means it will run out before a delivery ordered now could arrive; amber means
  reorder soon. Hover the figure for the calculation.
* **Stock:** record a *Receipt* (stock in, with an optional cost), *Issue*,
  *Waste / spoilage* or *Adjustment*.
* **Count:** enter what is physically on the shelf. The difference is posted
  as an adjustment.
* **Movements:** the full history of every change, with who made it and why.
  Movements cannot be edited or deleted; mistakes are corrected with a new
  movement.

## Suppliers and purchase orders (manager)

1. **Suppliers:** contacts and lead time (days from order to delivery).
   **Price list** links ingredients with the supplier's price, SKU and minimum
   order quantity.
2. **Purchase Orders → New purchase order:** pick the supplier and add lines in
   any unit. Prices default to the price list. Orders start as **drafts**.
3. **Submit** marks the order as sent. SmartPOS does not email or pay the
   supplier; send the order through your usual channel.
4. **Receive delivery:** enter what actually arrived. Short deliveries leave the
   rest outstanding, and an actual price that differs a lot from the ordered
   price is flagged before saving. Each delivery adds stock immediately.
5. Cancel a purchase order to drop outstanding quantities; delivered stock stays.

## Analytics and reports (manager)

**Analytics** shows net sales, orders, average order value and estimated gross
profit against the previous period of the same length. A period that ends
today is compared up to the same time of day. Below that are sales by day and
by hour (each chart has a **Table** view), categories, payment methods, top and
slow sellers, ingredient consumption, waste and purchases. Filter by date
range, category, product, payment method or order type.

**Reports** downloads CSV files (UTF-8, Thai text preserved): daily sales,
product sales, orders, inventory movements, inventory valuation and purchases.

## Forecasting and reorder suggestions (manager)

1. **Run forecast** compares four methods on your recent history (moving
   average, same weekday last week, day-of-week average, and a machine-learning
   model) and uses the most accurate one, or the one you pick.
2. **Overview** shows the model in use, its average error in portions per day,
   and a comparison table (MAE, RMSE, MAPE). Forecasts built on the demo data
   are labelled as such.
3. **Menu items** charts actual sales against what earlier forecasts predicted,
   then the next days. **Ingredients** converts the forecast through your
   recipes and shows the days of cover left.
4. **Reorder suggestions:** for each ingredient, the quantity needed to cover
   expected use until the next delivery plus safety stock, minus stock on hand
   and already on order, rounded up to the supplier's minimum. The ⓘ button
   shows the full calculation. **Approve**, **change the quantity** or
   **reject** each one, then select the approved ones and **Create draft POs**.
   Nothing is ordered until you submit those purchase orders yourself.

Forecasts are estimates from your own sales history. Holidays, events and
weather are not taken into account; adjust suggestions with your own judgement.

## AI assistant (manager)

Ask questions such as "What were today's sales?", "Which ingredients are
running low?" or "What should we reorder?". Answers use only your restaurant's
data, and each answer shows which data it used. The assistant cannot change
anything. Without an OpenAI key it runs in **offline mode** and answers common
questions with built-in rules.

## Staff (manager)

**User Management** lists staff with their role and last sign-in.
**Add staff** creates a cashier or kitchen account with an initial password
that you share privately; the person can change it from the account menu. Edit
a person to change their name or role, or turn off **Can sign in to this
restaurant**. The key button sets a new password and signs that person out
everywhere. Only administrators can create or change managers.

## Settings (manager)

* **Business & receipts:** names, tax ID, address, time zone (decides which
  day a late-night sale belongs to), order number prefix, and the receipt
  header and footer.
* **Tax & service:** VAT rate and whether menu prices include it; service
  charge (dine-in only or all orders, and whether VAT applies to it).
* **Stock, discounts & loyalty:** the largest discount a cashier may give,
  whether selling may push recipe stock below zero, and loyalty rules.
* **Payment methods:** add, rename, reorder or hide methods.
* **Preset discounts:** percentage or fixed, optionally manager-only.

## Administration (administrator)

* **Restaurants:** create a restaurant (default payment methods are added),
  add members by email, and deactivate or reactivate a restaurant.
* **Users:** every account on the installation. Create users, grant or remove
  administrator access, and deactivate accounts (this signs them out).
* **Audit log:** filter by restaurant and action, for example `order.` or `auth.`.

## Demo data

The **Baan Siam (Demo)** restaurant, marked with a *Demo data* badge, contains
synthetic menus, sales, purchases and forecasts for trying the system. It is
created in development installations and on public demo deployments, where it
is replaced with fresh data every night, so changes made there do not last.
