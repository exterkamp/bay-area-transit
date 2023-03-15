// Next.js API route support: https://nextjs.org/docs/api-routes/introduction
import type { NextApiRequest, NextApiResponse } from 'next'

import { Line } from '../../../../../types'

const axios = require('axios').default;

export default async function handler(
    req: NextApiRequest,
    res: NextApiResponse<Line[]>
) {
    // get the operators!
    let key = process.env.API_KEY;
    let base_url = process.env.BASE_URL;
    let api_path = process.env.API_PATH;


    let { operator_id } = req.query;

    if (operator_id instanceof Array) operator_id = operator_id[0]

    let lines = await getLines(operator_id!);

    if (lines.length === 0) {
        res.status(500);
        return;
    }

    res.status(200).json(lines)
}

export async function getLines(operator_id: string): Promise<Line[]> {
    let key = process.env.API_KEY;
    let base_url = process.env.BASE_URL;
    let api_path = process.env.API_PATH;

    let lines: Line[] = [];
    try {
        let url = new URL(api_path + '/lines',base_url);
        url.searchParams.append("api_key", key!)
        url.searchParams.append("operator_id", operator_id!)

        console.log(url);

        const response = await axios.get(url);

        for (let o of response.data) {
            lines.push({
                name: o.Name,
                id: o.Id,
            } as Line);
        }
    } catch (error) {
        return [];
    }
    return lines;
}