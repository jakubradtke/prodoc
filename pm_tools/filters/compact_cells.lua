-- Table cell clean-up for all pandoc calls of mmd2doc.py.
--
-- 1. Pandoc 3.12+ turns every cell of a table into Para once any cell holds several
--    blocks (compactifyTable). Para cells render with body text spacing, making such
--    tables much taller than before. A cell holding a single paragraph becomes Plain again.
--
-- 2. DOCX only: cell text gets the paragraph styles "Table Header" / "Table Body"
--    from reference.dotx (a table style alone cannot set cell font size in Word,
--    because the paragraph style of the text wins).
--
-- 3. Cell colour markers: a cell starting with "#AFA#", "#FFFFA0#" or "#Tomato#"
--    (hex digits or a CSS colour name) loses the marker. HTML/PDF cells get that
--    background colour; DOCX cells only lose the marker.

local is_docx = FORMAT:match("docx") ~= nil

-- Remove a leading "#colour#" marker from the cell and return the CSS colour, or nil
local function take_colour(cell)
  local first = cell.contents[1]
  if not first or (first.t ~= "Plain" and first.t ~= "Para") then return nil end
  local inlines = first.content
  if #inlines == 0 or inlines[1].t ~= "Str" then return nil end
  local name = inlines[1].text:match("^#(%w+)#$")
  if not name then return nil end
  inlines:remove(1)
  if #inlines > 0 and inlines[1].t == "Space" then inlines:remove(1) end
  if name:match("^%x+$") and (#name == 3 or #name == 6) then return "#" .. name end
  return name
end

local function style_rows(rows, style)
  for _, row in ipairs(rows) do
    for _, cell in ipairs(row.cells) do
      local colour = take_colour(cell)
      if colour and not is_docx then
        cell.attr.attributes["style"] = "background-color:" .. colour
      end
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
