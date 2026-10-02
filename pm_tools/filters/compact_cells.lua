-- Pandoc 3.12+ turns every cell of a table into Para once any cell holds several
-- blocks (compactifyTable). Para cells render with body text spacing (e.g. the
-- "First Paragraph" style in docx), making such tables much taller than before.
-- Restore compact cells: a cell holding a single paragraph becomes Plain again.
--
-- DOCX only: cell text gets the paragraph styles "Table Header" / "Table Body"
-- from reference.dotx (a table style alone cannot set cell font size in Word,
-- because the paragraph style of the text wins).

local is_docx = FORMAT:match("docx") ~= nil

local function style_rows(rows, style)
  for _, row in ipairs(rows) do
    for _, cell in ipairs(row.cells) do
      if is_docx then
        -- custom-style applies to Para only (Plain always gets "Compact"); the cell
        -- styles have compact spacing, so Para does not make the table taller
        for i, block in ipairs(cell.contents) do
          if block.t == "Plain" then
            cell.contents[i] = pandoc.Para(block.content)
          end
        end
        if #cell.contents > 0 then
          cell.contents = { pandoc.Div(cell.contents, pandoc.Attr("", {}, { ["custom-style"] = style })) }
        end
      elseif #cell.contents == 1 and cell.contents[1].t == "Para" then
        cell.contents[1] = pandoc.Plain(cell.contents[1].content)
      end
    end
  end
end

function Table(tbl)
  style_rows(tbl.head.rows, "Table Header")
  for _, body in ipairs(tbl.bodies) do
    style_rows(body.head, "Table Header")
    style_rows(body.body, "Table Body")
  end
  style_rows(tbl.foot.rows, "Table Body")
  return tbl
end
