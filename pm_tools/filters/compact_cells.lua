-- Pandoc 3.12+ turns every cell of a table into Para once any cell holds several
-- blocks (compactifyTable). Para cells render with body text spacing (e.g. the
-- "First Paragraph" style in docx), making such tables much taller than before.
-- Restore compact cells: a cell holding a single paragraph becomes Plain again.

local function compact_rows(rows)
  for _, row in ipairs(rows) do
    for _, cell in ipairs(row.cells) do
      if #cell.contents == 1 and cell.contents[1].t == "Para" then
        cell.contents[1] = pandoc.Plain(cell.contents[1].content)
      end
    end
  end
end

function Table(tbl)
  compact_rows(tbl.head.rows)
  for _, body in ipairs(tbl.bodies) do
    compact_rows(body.head)
    compact_rows(body.body)
  end
  compact_rows(tbl.foot.rows)
  return tbl
end
