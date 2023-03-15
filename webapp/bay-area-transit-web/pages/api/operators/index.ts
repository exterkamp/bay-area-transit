// Next.js API route support: https://nextjs.org/docs/api-routes/introduction
import type { NextApiRequest, NextApiResponse } from 'next'

import { Operator } from '../../../types'

const axios = require('axios').default;

export default async function handler(
    req: NextApiRequest,
    res: NextApiResponse<Operator[]>
) {
    // get the operators!
    let key = process.env.API_KEY;
    let base_url = process.env.BASE_URL;
    let api_path = process.env.API_PATH;

    let operators: Operator[] = [];

    try {
        let url = new URL(api_path + '/gtfsoperators',base_url);
        url.searchParams.append("api_key", key!)

        const response = await axios.get(url);

        for (let o of response.data) {
            operators.push({
                name: o.Name,
                id: o.Id,
            } as Operator);
        }
    } catch (error) {
        res.status(500);
        return;
    }

    res.status(200).json(operators)
}