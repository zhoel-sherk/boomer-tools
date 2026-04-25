import time
# import logger
import difflib

from text_grid import *
import cross_check

# -----------------------------------------------------------------------------

EOL = '\n'
PRE_EOL = '\n' # when \r\n, PRE block inserts empty lines when .html file is opened

def __html_title(content: str) -> str:
    # https://en.wikipedia.org/wiki/Web_colors
    # add the newlines so if copied to the clipboard, it will be somewhat readable
    return f'<h3 style="color: DarkSlateGray;">{content}</h3>{EOL}'

def __html_header(content: str) -> str:
    return f'<h5 style="color: DimGray;">{content}</h5>{EOL}'

def __html_section_begin() -> str:
    # https://www.w3schools.com/tags/tag_pre.asp
    return f'<pre style="font-family: Consolas, monospace; font-size: 80%">{EOL}'

def __html_section_end() -> str:
    return f'</pre>{EOL}'

def __html_p(content: str) -> str:
    # return f'<p style="font-size: 80%">{content}</p>{EOL}'
    return f'<p style="font-size: 80%">{content}</p>'

def __html_span_red(content: str) -> str:
    return f'<span style="color: IndianRed">{content}</span>'

def __html_span_green(content: str) -> str:
    return f'<span style="color: ForestGreen">{content}</span>'

def __html_span_blue(content: str) -> str:
    return f'<span style="color: RoyalBlue">{content}</span>'

def __html_span_gray(content: str) -> str:
    return f'<span style="color: Gray">{content}</span>'

def __format_comment_diff(designator: str, designator_w: int, bom_cmnt: str, bom_w: int, pnp_cmnt: str, pnp_footprint: str) -> str:
    bom_comment = ""
    pnp_comment = ""

    # Prepend the PnP footprint to the BOM comment so comparisons include the footprint.
    # Resulting string is "<footprint>_<bom_comment>", e.g. "C1206_100nF"
    if pnp_footprint:
        bom_cmnt = "_".join([pnp_footprint, bom_cmnt])

    # https://docs.python.org/3/library/difflib.html
    sm = difflib.SequenceMatcher(None, bom_cmnt, pnp_cmnt)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'replace':
            # a[i1:i2] should be replaced by b[j1:j2].
            bom_comment += __html_span_blue(bom_cmnt[i1:i2])
            pnp_comment += __html_span_blue(pnp_cmnt[j1:j2])
        elif tag == 'delete':
            # a[i1:i2] should be deleted. Note that j1 == j2 in this case.
            bom_comment += __html_span_red(bom_cmnt[i1:i2])
        elif tag == 'insert':
            # b[j1:j2] should be inserted at a[i1:i1]. Note that i1 == i2 in this case.
            pnp_comment += __html_span_green(pnp_cmnt[j1:j2])
        elif tag == 'equal':
            # a[i1:i2] == b[j1:j2] (the sub-sequences are equal).
            bom_comment += bom_cmnt[i1:i2]
            pnp_comment += pnp_cmnt[j1:j2]

    bom_comment += ' ' * max(0, bom_w - len(bom_cmnt))

    ### output:
    out = '{desgn:{w}}: {bom}{bom_comment} {pnp}{pnp_comment}{eol}'.format(
                desgn=designator, w=designator_w,
                bom=__html_span_gray('BOM='),
                bom_comment=bom_comment,
                pnp=__html_span_gray('PnP='),
                pnp_comment=pnp_comment,
                eol=PRE_EOL
            )
    # logger.debug(f"'{out}'")
    return out

def __format_distance(dsgn1: str, dsgn1_w: int, dsgn2: str, dsgn2_w: int, distance: float) -> str:
    ### output:
    # https://docs.python.org/3.9/library/string.html?=#format-specification-mini-language
    unit_mm = __html_span_gray("mm")
    out = '{dsgn1:>{w1}} <--> {dsgn2:{w2}} = {distance:.1f}{unit}{eol}'.format(
                dsgn1=dsgn1, w1=dsgn1_w,
                dsgn2=dsgn2, w2=dsgn2_w,
                distance=distance,
                unit=unit_mm,
                eol=PRE_EOL
            )
    # logger.debug(f"'{out}'")
    return out

# -----------------------------------------------------------------------------

def prepare_html_report(bom_name: str, pnp_names: tuple[str, str], min_distance: float | None, ccresult: cross_check.CrossCheckResult) -> str:
    # html/body tags are intentionally omitted for embedding/copying the report body.
    output = __html_title(f'Cross-check report for: <em>{bom_name}</em>')

    if pnp_names[1] == "":
        output += __html_p(f"PnP: <em><b>{pnp_names[0]}</b></em>")
    else:
        output += __html_p(f"PnP 1: <em><b>{pnp_names[0]}</b></em>")
        output += __html_p(f"PnP 2: <em><b>{pnp_names[1]}</b></em>")

    # https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes
    output += __html_p(f"Generated: <b>{time.strftime('%Y-%m-%d, %H:%M:%S')}</b>")

    ### 1st section:
    section = __html_header(f'BOM parts missing in the PnP: {len(ccresult.bom_parst_missing_in_pnp)}')
    section += __html_section_begin()
    # determine columns width
    dsgn1_w = 0
    for item in ccresult.bom_parst_missing_in_pnp:
        dsgn1_w = max(len(item[0]), dsgn1_w)
    # format the output
    for item in ccresult.bom_parst_missing_in_pnp:
        section += '{desgn:{w}}: {cmnt}{eol}'.format(
            desgn=item[0], w=dsgn1_w, cmnt=item[1], eol=PRE_EOL
        )
    section += __html_section_end()
    output += section

    ### 2nd section:
    section = __html_header(f'PnP parts missing in the BOM: {len(ccresult.pnp_parst_missing_in_bom)}')
    section += __html_section_begin()
    # determine columns width
    dsgn1_w = 0
    for pnp_part in ccresult.pnp_parst_missing_in_bom:
        dsgn1_w = max(len(pnp_part[0]), dsgn1_w)
    # format the output
    for pnp_part in ccresult.pnp_parst_missing_in_bom:
        section += '{desgn:{w}}: {cmnt}{eol}'.format(
            desgn=pnp_part[0], w=dsgn1_w, cmnt=pnp_part[1], eol=PRE_EOL
        )
    section += __html_section_end()
    output += section

    ### 3rd section:
    section = __html_header(f'BOM and PnP comment mismatch: {len(ccresult.parts_comment_mismatch)}')
    section += __html_section_begin()
    # determine columns width
    dsgn1_w = 0
    bom_w = 0
    for item in ccresult.parts_comment_mismatch:
        dsgn1_w = max(len(item[0]), dsgn1_w)
        bom_w = max(len(item[1]) + 2, bom_w)
    # format the output
    for item in ccresult.parts_comment_mismatch:
        section += __format_comment_diff(item[0], dsgn1_w,
                                    item[1], bom_w,
                                    item[2],
                                    item[3])
    section += __html_section_end()
    output += section

    ### 4th section:
    if min_distance is None:
        section = __html_header(f'PnP overlapping components check: Disabled')
    else:
        section = __html_header(f'PnP overlapping components (distance between centers < {min_distance}mm): {len(ccresult.parts_coord_conflicts)}')
    section += __html_section_begin()
    # determine columns width
    dsgn1_w = 0
    dsgn2_w = 0
    for item in ccresult.parts_coord_conflicts:
        dsgn1_w = max(len(item[0]), dsgn1_w)
        dsgn2_w = max(len(item[1]), dsgn2_w)
    # format the output
    for item in ccresult.parts_coord_conflicts:
        section += __format_distance(item[0], dsgn1_w, item[1], dsgn2_w, item[2])

    section += __html_section_end()
    output += section

    ### 5th section:
    section = __html_header(f'PnP duplicate coordinates (exact match): {len(ccresult.parts_duplicate_coords)}')
    section += __html_section_begin()
    # determine columns width
    dsgn1_w = 0
    dsgn2_w = 0
    for item in ccresult.parts_duplicate_coords:
        dsgn1_w = max(len(item[0]), dsgn1_w)
        dsgn2_w = max(len(item[1]), dsgn2_w)
    # format the output
    for item in ccresult.parts_duplicate_coords:
        section += '{dsgn1:>{w1}} <--> {dsgn2:{w2}} = ({x:.1f}, {y:.1f}){eol}'.format(
            dsgn1=item[0], w1=dsgn1_w,
            dsgn2=item[1], w2=dsgn2_w,
            x=item[2], y=item[3],
            eol=PRE_EOL
        )

    section += __html_section_end()
    output += section

    # html block is ready
    return output
