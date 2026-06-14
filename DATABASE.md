# Chinook DB (demo) — Toàn bộ dữ liệu

> File: `mcp-servers/invoice/data/chinook.db` (SQLite)
> Đây là bản Chinook **rút gọn** dùng cho demo Music Store Agent.
> Cập nhật: 2026-06-15. Lưu ý: dữ liệu Invoice/InvoiceLine **thay đổi khi refund** (refund xóa hết InvoiceLine và set Total = 0).

## Tổng quan các bảng

| Bảng | Số dòng |
|---|---|
| Artist | 10 |
| Album | 12 |
| Track | 20 |
| Genre | 5 |
| Customer | 10 |
| Invoice | 10 |
| InvoiceLine | 44 |

---

## Artist (10)

| ArtistId | Name |
|---|---|
| 1 | AC/DC |
| 2 | The Beatles |
| 3 | Metallica |
| 4 | Led Zeppelin |
| 5 | Pink Floyd |
| 6 | Nirvana |
| 7 | The Rolling Stones |
| 8 | Queen |
| 9 | David Bowie |
| 10 | Radiohead |

> Ghi chú: Rolling Stones, Queen, David Bowie, Radiohead **có trong bảng Artist nhưng không có Album/Track** nào.

---

## Album (12)

| AlbumId | Title | Artist |
|---|---|---|
| 1 | Back in Black | AC/DC |
| 2 | Highway to Hell | AC/DC |
| 3 | Abbey Road | The Beatles |
| 4 | Let It Be | The Beatles |
| 5 | Master of Puppets | Metallica |
| 6 | Metallica (Black Album) | Metallica |
| 7 | Led Zeppelin IV | Led Zeppelin |
| 8 | Physical Graffiti | Led Zeppelin |
| 9 | The Dark Side of the Moon | Pink Floyd |
| 10 | Wish You Were Here | Pink Floyd |
| 11 | Nevermind | Nirvana |
| 12 | In Utero | Nirvana |

> Ghi chú: "Physical Graffiti" và "In Utero" có trong Album nhưng **không có Track** nào.

---

## Track (20)

| TrackId | Track | Album | Artist | UnitPrice |
|---|---|---|---|---|
| 1 | Hells Bells | Back in Black | AC/DC | $0.99 |
| 2 | Shoot to Thrill | Back in Black | AC/DC | $0.99 |
| 3 | Back in Black | Back in Black | AC/DC | $0.99 |
| 4 | Highway to Hell | Highway to Hell | AC/DC | $0.99 |
| 5 | Come as You Are | Highway to Hell | AC/DC | $0.99 |
| 6 | Come Together | Abbey Road | The Beatles | $0.99 |
| 7 | Something | Abbey Road | The Beatles | $0.99 |
| 8 | Let It Be | Let It Be | The Beatles | $0.99 |
| 9 | Battery | Master of Puppets | Metallica | $0.99 |
| 10 | Master of Puppets | Master of Puppets | Metallica | $0.99 |
| 11 | Enter Sandman | Metallica (Black Album) | Metallica | $0.99 |
| 12 | Nothing Else Matters | Metallica (Black Album) | Metallica | $0.99 |
| 13 | Stairway to Heaven | Led Zeppelin IV | Led Zeppelin | $0.99 |
| 14 | Black Dog | Led Zeppelin IV | Led Zeppelin | $0.99 |
| 15 | Money | The Dark Side of the Moon | Pink Floyd | $0.99 |
| 16 | Time | The Dark Side of the Moon | Pink Floyd | $0.99 |
| 17 | Smells Like Teen Spirit | Nevermind | Nirvana | $0.99 |
| 18 | Come as You Are | Nevermind | Nirvana | $0.99 |
| 19 | Wish You Were Here | Wish You Were Here | Pink Floyd | $0.99 |
| 20 | Comfortably Numb | The Dark Side of the Moon | Pink Floyd | $0.99 |

> Ghi chú: tên track "Come as You Are" xuất hiện 2 lần — một của AC/DC (TrackId 5) và một của Nirvana (TrackId 18). Mọi track đều giá $0.99.

---

## Customer (10)

| CustomerId | Name | Phone | Email |
|---|---|---|---|
| 1 | Leonie Kohler | +49 0711 2842222 | leonekohler@surfeu.de |
| 2 | Bjorn Hansen | +47 22 44 68 68 | bjorn.hansen@yahoo.no |
| 3 | Francois Tremblay | 1 (514) 721-4711 | ftremblay@gmail.com |
| 4 | Helena Holy | +420 2 4177 0449 | hholy@gmail.com |
| 5 | Hugh O'Reilly | 1 (800) 555-0116 | hughoreilly@apple.com |
| 6 | Lucas Mancini | +39 06 39733434 | lucas.mancini@yahoo.it |
| 7 | Johannes Van der Berg | +31 (0)20 6221782 | johavanderberg@yahoo.nl |
| 8 | Daan Peeters | +32 02 219 03 03 | daan_peeters@apple.be |
| 9 | Karin Wied | +46 08-651 52 52 | karin.wied@apple.se |
| 10 | Eduardo Martins | +55 (12) 3923-5555 | eduardo@woodstock.com.br |

> Mỗi khách hàng có đúng **1 hóa đơn** (InvoiceId = CustomerId).

---

## Invoice (10)

| InvoiceId | Date | Customer | Total | Số dòng | Trạng thái |
|---|---|---|---|---|---|
| 1 | 2021-01-01 | Leonie Kohler | $0.00 | 0 | **ĐÃ REFUND** |
| 2 | 2021-01-02 | Bjorn Hansen | $0.00 | 0 | **ĐÃ REFUND** |
| 3 | 2021-01-03 | Francois Tremblay | $1.98 | 2 | còn hiệu lực |
| 4 | 2021-01-04 | Helena Holy | $7.92 | 8 | còn hiệu lực |
| 5 | 2021-01-05 | Hugh O'Reilly | $5.94 | 6 | còn hiệu lực |
| 6 | 2021-02-01 | Lucas Mancini | $1.98 | 2 | còn hiệu lực |
| 7 | 2021-02-02 | Johannes Van der Berg | $13.86 | 14 | còn hiệu lực |
| 8 | 2021-02-03 | Daan Peeters | $3.96 | 4 | còn hiệu lực |
| 9 | 2021-02-04 | Karin Wied | $5.94 | 6 | còn hiệu lực |
| 10 | 2021-02-05 | Eduardo Martins | $1.98 | 2 | còn hiệu lực |

> Hóa đơn #1 và #2 đang ở trạng thái đã hoàn tiền (Total = 0, không còn InvoiceLine).
> Các hóa đơn còn lại còn nguyên sản phẩm. Tổng số InvoiceLine hiện tại = 44.

---

## InvoiceLine (44) — chi tiết theo hóa đơn

**Invoice #3 — Francois Tremblay ($1.98)**
- Hells Bells — AC/DC × 1 @ $0.99
- Shoot to Thrill — AC/DC × 1 @ $0.99

**Invoice #4 — Helena Holy ($7.92)**
- Back in Black — AC/DC × 1 @ $0.99
- Highway to Hell — AC/DC × 1 @ $0.99
- Come as You Are — AC/DC × 1 @ $0.99
- Come Together — The Beatles × 1 @ $0.99
- Something — The Beatles × 1 @ $0.99
- Let It Be — The Beatles × 1 @ $0.99
- Battery — Metallica × 1 @ $0.99
- Master of Puppets — Metallica × 1 @ $0.99

**Invoice #5 — Hugh O'Reilly ($5.94)**
- Enter Sandman — Metallica × 1 @ $0.99
- Nothing Else Matters — Metallica × 1 @ $0.99
- Stairway to Heaven — Led Zeppelin × 1 @ $0.99
- Black Dog — Led Zeppelin × 1 @ $0.99
- Money — Pink Floyd × 1 @ $0.99
- Time — Pink Floyd × 1 @ $0.99

**Invoice #6 — Lucas Mancini ($1.98)**
- Smells Like Teen Spirit — Nirvana × 1 @ $0.99
- Come as You Are — Nirvana × 1 @ $0.99

**Invoice #7 — Johannes Van der Berg ($13.86)**
- Hells Bells, Shoot to Thrill, Back in Black, Highway to Hell, Come as You Are — AC/DC (5 track)
- Come Together, Something, Let It Be — The Beatles (3 track)
- Battery, Master of Puppets, Enter Sandman, Nothing Else Matters — Metallica (4 track)
- Stairway to Heaven, Black Dog — Led Zeppelin (2 track)
- (tổng 14 dòng, mỗi dòng $0.99)

**Invoice #8 — Daan Peeters ($3.96)**
- Money — Pink Floyd × 1 @ $0.99
- Time — Pink Floyd × 1 @ $0.99
- Smells Like Teen Spirit — Nirvana × 1 @ $0.99
- Come as You Are — Nirvana × 1 @ $0.99

**Invoice #9 — Karin Wied ($5.94)**
- Wish You Were Here — Pink Floyd × 1 @ $0.99
- Comfortably Numb — Pink Floyd × 1 @ $0.99
- Hells Bells, Shoot to Thrill, Back in Black, Highway to Hell — AC/DC (4 track)

**Invoice #10 — Eduardo Martins ($1.98)**
- Come as You Are — AC/DC × 1 @ $0.99
- Come Together — The Beatles × 1 @ $0.99

**Invoice #1 (Leonie Kohler) và #2 (Bjorn Hansen):** không có dòng nào — đã refund.

---

## Gợi ý câu hỏi test theo dữ liệu

| Mục đích | Câu hỏi | Kết quả mong đợi |
|---|---|---|
| QnA catalog | `What albums does AC/DC have?` | Back in Black, Highway to Hell |
| Search — chưa refund | `Search invoices for Helena Holy` | Invoice #4, 8 track |
| Search — đã refund | `Search invoices for Bjorn Hansen` | Invoice #2 `[REFUNDED — no items]` |
| Search — không tồn tại | `Search invoices for John Doe` | `No customer found matching 'John Doe'.` |
| Refund theo ID | `Refund invoice 3` | (xem ghi chú giới hạn của LangGraph refund_node bên dưới) |
| Refund theo tên | `Refund invoice for Francois Tremblay` | Refund Invoice #3 ($1.98) |

> **Lưu ý giới hạn (LangGraph `refund_node`):** node này refund theo **tên khách hàng**, không theo **ID hóa đơn**. Câu "Refund invoice 3" không có tên người → tìm khách "Refund invoice 3" → không thấy → hỏi lại. Muốn refund đúng, hãy nói kèm tên khách (vd "Refund invoice for Francois Tremblay") hoặc dùng luồng **NAT** (ReAct gọi thẳng tool `invoice_refund` với invoice_id).
